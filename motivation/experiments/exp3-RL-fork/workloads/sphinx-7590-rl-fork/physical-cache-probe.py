#!/usr/bin/env python3
"""Keep a guest PFN marker alive and export file-LRU PFNs for host de-duplication."""
from __future__ import annotations

import array
import ctypes
import json
import mmap
import os
import struct
import sys
import time
from pathlib import Path


def main() -> None:
    sandbox_id = sys.argv[1]
    output = Path("/dev/shm") / f"mixfs-exp5-{sandbox_id}"
    output.mkdir(exist_ok=True)
    (output / "marker.json").unlink(missing_ok=True)
    (output / "file-pfns.bin").unlink(missing_ok=True)
    marker = mmap.mmap(-1, 4096)
    marker_bytes = f"MIXFS-EXP5-PFN:{sandbox_id}".encode()
    marker[:len(marker_bytes)] = marker_bytes
    address = ctypes.addressof(ctypes.c_char.from_buffer(marker))
    if ctypes.CDLL(None).mlock(ctypes.c_void_p(address), ctypes.c_size_t(4096)) != 0:
        raise OSError("mlock marker failed")
    with open("/proc/self/pagemap", "rb", buffering=0) as handle:
        entry = struct.unpack("Q", os.pread(handle.fileno(), 8, address // 4096 * 8))[0]
    marker_pfn = entry & ((1 << 55) - 1)
    if not entry & (1 << 63) or marker_pfn == 0:
        raise RuntimeError("guest pagemap did not expose resident marker PFN")

    # 4 GiB RAM: 0..3 GiB and 4..5 GiB guest physical regions.
    limit = 0x140000000 // 4096
    with open("/proc/kpageflags", "rb", buffering=0) as handle:
        flags = os.pread(handle.fileno(), limit * 8, 0)
    if len(flags) != limit * 8:
        raise RuntimeError("short /proc/kpageflags read")
    pfns = array.array("I")
    for pfn, (value,) in enumerate(struct.iter_unpack("Q", flags)):
        # LRU pages without ANON or SWAPBACKED are the guest's file cache.
        if value & (1 << 5) and not value & (1 << 12) and not value & (1 << 14):
            pfns.append(pfn)
    (output / "file-pfns.bin").write_bytes(pfns.tobytes())
    (output / "marker.json").write_text(json.dumps({
        "sandbox_id": sandbox_id, "marker_pfn": marker_pfn,
        "marker_ascii": marker_bytes.decode(), "file_pfn_count": len(pfns),
    }) + "\n")
    while True:
        time.sleep(30)


if __name__ == "__main__":
    main()
