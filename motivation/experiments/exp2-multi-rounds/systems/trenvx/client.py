#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import tarfile
import time
from pathlib import Path

from sandbox_sdk.sandbox import Sandbox
import sandbox_sdk.sandbox.sandbox_connection as sandbox_connection


def copy_reflink(source: Path, target: Path) -> None:
    subprocess.run(
        ["cp", "--reflink=auto", "--preserve=mode,timestamps", str(source), str(target)],
        check=True,
    )


def promote_template(data_root: Path, current: str, next_id: str, sandbox_id: str, snapshot: Path) -> None:
    current_dir = data_root / "templates" / current
    next_dir = data_root / "templates" / next_id
    instance = current_dir / "instances" / sandbox_id
    image = next_dir / "image"
    if next_dir.exists():
        raise RuntimeError(f"temporary template already exists: {next_dir}")
    image.mkdir(parents=True)
    copy_reflink(current_dir / "image" / "rootfs.ext4", image / "rootfs.ext4")
    copy_reflink(instance / "writable-rootfs.ext4", image / "writable-rootfs.ext4")
    for source in snapshot.iterdir():
        if source.is_file():
            copy_reflink(source, image / source.name)
    # Cloud Hypervisor serializes absolute device paths in both snapshot JSON
    # files. The promoted template is mounted at a different private path, so
    # rewrite the complete private directory (writable disk and pmem rootfs).
    old_private = str(current_dir / "run")
    new_private = str(next_dir / "run")
    for name in ("config.json", "state.json"):
        snapshot_json = image / name
        content = snapshot_json.read_text(encoding="utf-8")
        if old_private not in content:
            raise RuntimeError(f"{name} does not reference expected private path: {old_private}")
        snapshot_json.write_text(content.replace(old_private, new_private), encoding="utf-8")
        if old_private in snapshot_json.read_text(encoding="utf-8"):
            raise RuntimeError(f"old private path remains in promoted {name}")
    # Ensure the bind-mount placeholder expected by the orchestrator exists.
    (image / "vmlinux").touch(exist_ok=True)
    config = (current_dir / "template.toml").read_text(encoding="utf-8")
    old_template_line = f'template_id = "{current}"'
    if old_template_line not in config:
        raise RuntimeError(f"template config does not identify {current}")
    config = config.replace(old_template_line, f'template_id = "{next_id}"', 1)
    (next_dir / "template.toml").write_text(config, encoding="utf-8")


async def wait_output(process, timeout: float):
    output = await process.wait(timeout=timeout)
    if output.exit_code != 0:
        raise RuntimeError(f"guest command failed ({output.exit_code}): {output.stderr}")
    return output


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=3600)
    args = parser.parse_args()
    sandbox_connection.ORCHESTRATOR_PORT = int(os.environ["ORCHESTRATOR_PORT"])

    def direct_guest_url(self, port=None):
        if self._sandbox is None:
            raise RuntimeError("sandbox is not running")
        return f"{self._sandbox.private_ip}:{port or 49982}"

    sandbox_connection.SandboxConnection.get_sbx_url = direct_guest_url
    raw = args.raw_dir.resolve()
    (raw / "rounds").mkdir(parents=True, exist_ok=True)
    transitions = raw / "transitions.tsv"
    transitions.write_text("after_round\tcheckpoint_ns\trestore_ns\timage_rebuild_ns\n")
    host_pmem = raw / "host-pmem.tsv"
    host_pmem.write_text("round\trootfs_path\tmapping_bytes\n", encoding="utf-8")
    created_templates: list[Path] = []
    sandbox: Sandbox | None = None
    current_template = args.template
    try:
        # Initial startup is outside the workload window and is not recorded as action latency.
        sandbox = await Sandbox.create(template=current_template, target_addr="127.0.0.1", timeout=args.timeout)
        with (raw / "sandbox-ids.txt").open("a", encoding="utf-8") as handle:
            handle.write(f"{sandbox.id}\n")
        for round_no in range(1, 5):
            # CH exposes the read-only rootfs as /dev/pmem0.  This is a host
            # file mapping separate from guest RAM, so record its capacity in
            # a separate host metric instead of folding it into MemTotal.
            rootfs = args.data_root / "templates" / current_template / "instances" / sandbox.id / "rootfs.ext4"
            with host_pmem.open("a", encoding="utf-8") as handle:
                handle.write(f"{round_no}\t{rootfs}\t{rootfs.stat().st_size}\n")
            process = await sandbox.simple_process.start(
                "/bin/bash /opt/mixfs/guest-runner.sh",
                user="root",
                env_vars={
                    "ROUND": str(round_no),
                    "ACTIONS_ROOT": "/opt/mixfs/rounds",
                    "OUTPUT_DIR": f"/tmp/mixfs-exp2/round-{round_no}",
                    "ACTION_TIMEOUT_SECONDS": os.environ["ACTION_TIMEOUT_SECONDS"],
                    "MEMORY_SAMPLE_INTERVAL_SECONDS": os.environ["MEMORY_SAMPLE_INTERVAL_SECONDS"],
                },
            )
            output = await wait_output(process, args.timeout)
            round_dir = raw / "rounds" / str(round_no)
            round_dir.mkdir()
            (round_dir / "runner.stdout.log").write_text(output.stdout, encoding="utf-8")
            (round_dir / "runner.stderr.log").write_text(output.stderr, encoding="utf-8")
            pack = await sandbox.simple_process.start(
                f"tar -C /tmp/mixfs-exp2/round-{round_no} -czf /tmp/mixfs-round-{round_no}.tar.gz .",
                user="root",
            )
            await wait_output(pack, args.timeout)
            archive = round_dir / "artifacts.tar.gz"
            archive.write_bytes(await sandbox.download_file(f"/tmp/mixfs-round-{round_no}.tar.gz", timeout=args.timeout))
            with tarfile.open(archive, "r:gz") as handle:
                handle.extractall(round_dir, filter="data")

            drop = await sandbox.simple_process.start("sync; echo 3 > /proc/sys/vm/drop_caches", user="root")
            await wait_output(drop, args.timeout)
            start = time.time_ns()
            response = await sandbox.snapshot(delete=False, timeout=args.timeout)
            checkpoint_ns = time.time_ns() - start
            snapshot_path = Path(response.path)
            (round_dir / "checkpoint-path.txt").write_text(f"{snapshot_path}\n", encoding="utf-8")
            next_template = f"{args.template}-{raw.name}-r{round_no}"
            start = time.time_ns()
            promote_template(args.data_root, current_template, next_template, sandbox.id, snapshot_path)
            rebuild_ns = time.time_ns() - start
            created_templates.append(args.data_root / "templates" / next_template)
            shutil.rmtree(snapshot_path)
            await Sandbox.kill(sandbox.id, target_addr="127.0.0.1")
            # Upstream Delete returns before its asynchronous cgroup/network cleanup.
            await asyncio.sleep(1.5)
            await sandbox.close()
            sandbox = None

            start = time.time_ns()
            sandbox = await Sandbox.create(template=next_template, target_addr="127.0.0.1", timeout=args.timeout)
            restore_ns = time.time_ns() - start
            current_template = next_template
            with (raw / "sandbox-ids.txt").open("a", encoding="utf-8") as handle:
                handle.write(f"{sandbox.id}\n")
            with transitions.open("a", encoding="utf-8") as handle:
                handle.write(f"{round_no}\t{checkpoint_ns}\t{restore_ns}\t{rebuild_ns}\n")
        return 0
    finally:
        if sandbox is not None:
            try:
                await Sandbox.kill(sandbox.id, target_addr="127.0.0.1")
                await asyncio.sleep(1.5)
            finally:
                await sandbox.close()
        for path in reversed(created_templates):
            shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
