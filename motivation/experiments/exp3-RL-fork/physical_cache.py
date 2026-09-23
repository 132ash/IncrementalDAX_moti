#!/usr/bin/env python3
"""Join guest file-cache PFNs to resident host PFNs and de-duplicate COW pages."""
from __future__ import annotations

import array
import json
import os
import re
import struct
import sys
import time
from pathlib import Path


def slots(path: Path) -> dict[int, list[tuple[int, int, int]]]:
    latest: dict[tuple[int, int], tuple[int, int, int]] = {}
    for line in path.read_text().splitlines():
        fields = line.split("\t")
        if len(fields) != 5 or not fields[0].isdigit():
            continue
        pid, slot = int(fields[0]), int(fields[1])
        guest, size, host = (int(value, 16) for value in fields[2:])
        if size and guest < 0x140000000:
            latest[pid, slot] = (guest, size, host)
    by_pid: dict[int, list[tuple[int, int, int]]] = {}
    for (pid, _), item in latest.items():
        if Path(f"/proc/{pid}/comm").exists():
            by_pid.setdefault(pid, []).append(item)
    return by_pid


def host_address(pfn: int, regions: list[tuple[int, int, int]]) -> int | None:
    guest_addr = pfn * 4096
    for guest, size, host in regions:
        if guest <= guest_addr < guest + size:
            return host + guest_addr - guest
    return None


def dax_pss_kib(pid: int) -> int:
    total = 0
    candidate = False
    for line in Path(f"/proc/{pid}/smaps").read_text().splitlines():
        if re.match(r"^[0-9a-f]+-[0-9a-f]+\s", line):
            pathname = line.split(maxsplit=5)[-1] if len(line.split(maxsplit=5)) > 5 else ""
            name = Path(pathname).name
            candidate = name == "rootfs.ext4" or (name.startswith("checkpoint-") and name.endswith(".ext4"))
        elif candidate and line.startswith("Pss:"):
            total += int(line.split()[1])
    return total


def vmm_pss_kib(pid: int) -> int:
    for line in Path(f"/proc/{pid}/smaps_rollup").read_text().splitlines():
        if line.startswith("Pss:"):
            return int(line.split()[1])
    raise RuntimeError(f"missing VMM PSS for pid {pid}")


def main(raw: Path, expected: int = 7, probes_dir: Path | None = None, output_path: Path | None = None) -> None:
    guest_probes = sorted((probes_dir or raw / "host/probes").glob("*/marker.json"))
    if len(guest_probes) != expected:
        raise RuntimeError(f"expected {expected} guest probes, got {len(guest_probes)}")
    regions = slots(raw / "host/kvm-slots.tsv")
    matched: dict[str, int] = {}
    all_host_cache_pfns: set[int] = set()
    logical_pages = 0
    resident_guest_pages = 0
    for probe in guest_probes:
        marker = json.loads(probe.read_text())
        sandbox_id = marker["sandbox_id"]
        guest_pfn = marker["marker_pfn"]
        needle = marker["marker_ascii"].encode()
        matches = []
        for pid, memory_regions in regions.items():
            address = host_address(guest_pfn, memory_regions)
            if address is None:
                continue
            try:
                fd = os.open(f"/proc/{pid}/mem", os.O_RDONLY)
                try:
                    if os.pread(fd, len(needle), address) == needle:
                        matches.append(pid)
                finally:
                    os.close(fd)
            except OSError:
                continue
        if len(matches) != 1:
            raise RuntimeError(f"marker {sandbox_id} matched {matches}; KVM slots may be incomplete")
        pid = matches[0]
        if pid in matched.values():
            raise RuntimeError(f"VMM pid {pid} matched multiple sandboxes")
        matched[sandbox_id] = pid
        file_pfns = array.array("I")
        file_pfns.frombytes((probe.parent / "file-pfns.bin").read_bytes())
        logical_pages += len(file_pfns)
        # Read one 8-byte pagemap entry per guest RAM page in large batches.
        host_maps: list[tuple[int, int, bytes]] = []
        fd = os.open(f"/proc/{pid}/pagemap", os.O_RDONLY)
        try:
            for guest, size, host in regions[pid]:
                page_count = size // 4096
                page_entries = os.pread(fd, page_count * 8, host // 4096 * 8)
                if len(page_entries) != page_count * 8:
                    raise RuntimeError(f"short host pagemap for pid {pid}")
                host_maps.append((guest, size, page_entries))
        finally:
            os.close(fd)
        for guest_pfn in file_pfns:
            guest_addr = guest_pfn * 4096
            for guest, size, entries in host_maps:
                if guest <= guest_addr < guest + size:
                    index = (guest_addr - guest) // 4096
                    entry = struct.unpack_from("Q", entries, index * 8)[0]
                    if entry & (1 << 63):
                        host_pfn = entry & ((1 << 55) - 1)
                        if not host_pfn:
                            raise RuntimeError("host pagemap hides PFNs; physical de-duplication unavailable")
                        all_host_cache_pfns.add(host_pfn)
                        resident_guest_pages += 1
                    break
    if len(matched) != expected:
        raise RuntimeError("incomplete sandbox-to-VMM mapping")
    dax_kib = sum(dax_pss_kib(pid) for pid in matched.values())
    vmm_kib = sum(vmm_pss_kib(pid) for pid in matched.values())
    result = {
        "sample_time_ns": time.time_ns(),
        "sandbox_to_vmm_pid": matched,
        "guest_file_cache_host_physical_mib": len(all_host_cache_pfns) * 4 / 1024,
        "dax_file_host_physical_pss_mib": dax_kib / 1024,
        "page_cache_host_physical_mib": (len(all_host_cache_pfns) * 4 + dax_kib) / 1024,
        "sandbox_vmm_host_physical_pss_mib": vmm_kib / 1024,
        "guest_file_cache_logical_pages": logical_pages,
        "guest_file_cache_resident_mappings": resident_guest_pages,
    }
    if result["page_cache_host_physical_mib"] > result["sandbox_vmm_host_physical_pss_mib"] * 1.01:
        raise RuntimeError("page cache exceeds total VMM PSS; mapping attribution invalid")
    (output_path or raw / "host/physical-memory.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve(), int(sys.argv[2]) if len(sys.argv) > 2 else 7,
         Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else None,
         Path(sys.argv[4]).resolve() if len(sys.argv) > 4 else None)
