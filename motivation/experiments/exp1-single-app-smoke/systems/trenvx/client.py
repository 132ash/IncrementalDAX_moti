#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
import tarfile
import time
from pathlib import Path

from sandbox_sdk.sandbox import Sandbox
import sandbox_sdk.sandbox.sandbox_connection as sandbox_connection


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--timeout", required=True, type=float)
    args = parser.parse_args()
    # Upstream SDK hard-codes 5000; keep the runtime source untouched and make
    # the experiment port explicit so it can coexist with local services.
    sandbox_connection.ORCHESTRATOR_PORT = int(os.environ["ORCHESTRATOR_PORT"])
    # The upstream SDK normally routes envd through its optional nginx sidecar.
    # This single-host experiment reaches the private guest address directly.
    def direct_guest_url(self, port=None):
        if self._sandbox is None:
            raise RuntimeError("sandbox is not running")
        return f"{self._sandbox.private_ip}:{port or 49982}"

    sandbox_connection.SandboxConnection.get_sbx_url = direct_guest_url
    raw = args.raw_dir.resolve()
    raw.mkdir(parents=True, exist_ok=True)
    sandbox: Sandbox | None = None
    try:
        start = time.time_ns()
        sandbox = await Sandbox.create(
            template=args.template, target_addr="127.0.0.1", timeout=args.timeout
        )
        (raw / "cold-start-duration-ns.txt").write_text(
            f"{time.time_ns() - start}\n", encoding="utf-8"
        )
        (raw / "sandbox-id.txt").write_text(f"{sandbox.id}\n", encoding="utf-8")
        while not (raw / ".run-replay").exists():
            await asyncio.sleep(0.02)
        process = await sandbox.simple_process.start(
            "bash /opt/mixfs/guest-runner.sh",
            user="root",
            env_vars={
                "ACTION_TIMEOUT_SECONDS": os.environ["ACTION_TIMEOUT_SECONDS"],
                "MEMORY_SAMPLE_INTERVAL_SECONDS": os.environ["MEMORY_SAMPLE_INTERVAL_SECONDS"],
                "DROP_GUEST_CACHES": os.environ["DROP_GUEST_CACHES"],
                "ACTIONS_DIR": "/opt/mixfs/actions",
                "OUTPUT_DIR": "/tmp/mixfs-replay",
            },
        )
        output = await process.wait(timeout=args.timeout)
        (raw / "replay-command-exit-code.txt").write_text(
            f"{output.exit_code}\n", encoding="utf-8"
        )
        (raw / "replay-command.stdout.log").write_text(output.stdout, encoding="utf-8")
        (raw / "replay-command.stderr.log").write_text(output.stderr, encoding="utf-8")
        pack = await sandbox.simple_process.start(
            "tar -C /tmp -czf /tmp/mixfs-replay.tar.gz mixfs-replay",
            user="root",
        )
        packed = await pack.wait(timeout=args.timeout)
        if packed.exit_code != 0:
            raise RuntimeError(f"tar failed: {packed.stderr}")
        archive = raw / "replay.tar.gz"
        archive.write_bytes(
            await sandbox.download_file("/tmp/mixfs-replay.tar.gz", timeout=args.timeout)
        )
        with tarfile.open(archive, "r:gz") as handle:
            handle.extractall(raw, filter="data")
        (raw / "mixfs-replay").rename(raw / "replay")
        return int(output.exit_code or 0)
    finally:
        if sandbox is not None:
            sandbox_id = sandbox.id
            try:
                await Sandbox.kill(sandbox_id, target_addr="127.0.0.1")
                (raw / "cleanup.log").write_text(
                    f"deleted={sandbox_id}\n", encoding="utf-8"
                )
            finally:
                await sandbox.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
