#!/usr/bin/env python3
"""Replay one frozen seven-rollout trace under GRPO, BPO, or prefix caching."""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import time
import tempfile
from pathlib import Path

from checkpoint_dax import archive_upper, build_layer

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
WORKLOAD_NAME = os.environ.get("WORKLOAD_NAME", "prettier-6604-rl-fork")
WORKLOAD = ROOT / "workloads" / WORKLOAD_NAME
ROLES = ("backbone", "early_1", "early_2", "early_3", "late_1", "late_2", "late_3")


def shell(*args: str, capture: bool = True) -> str:
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE if capture else None)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {args[:3]}\nstdout: {(result.stdout or '')[-2000:]}\nstderr: {(result.stderr or '')[-2000:]}")
    return result.stdout.strip() if capture else ""


class Controller:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.raw = args.raw_dir.resolve()
        self.raw.mkdir(parents=True, exist_ok=True)
        (self.raw / "host").mkdir(exist_ok=True)
        self.phase_file = self.raw / ".phase"
        self.rollouts = json.loads((WORKLOAD / "rollouts.json").read_text())
        self.live: dict[str, object] = {}
        self.templates: list[Path] = []
        self.agentenv_templates: list[str] = []
        self._layers: dict[str, list[str]] = {}
        self._active_layer: dict[str, str | None] = {}
        self.counter = 0
        self.physical_sample_count = 0
        self.physical_sample_lock = asyncio.Lock()
        self.sdk = None
        self.data_root = Path(os.environ.get("DATA_ROOT", "/var/lib/trenvx-exp5-cow"))
        self.base_template = os.environ.get("TEMPLATE_ID", "prettier-6604-exp5-rl-fork-ch-layered")
        self.image = os.environ.get("WORKLOAD_IMAGE", "ghcr.io/timesler/swe-polybench.eval.x86_64.prettier__prettier-6604@sha256:8159d38fcbd6d5f09402d93d3e15cf2a891058ddd835a224f1d6b3357a87cc94")
        self.task = json.loads((WORKLOAD / "task.json").read_text()) if (WORKLOAD / "task.json").exists() else {
            "instance_id": "prettier__prettier-6604",
            "title": "Prettier TypeScript double-parenthesis semantic repair",
            "url": "https://github.com/prettier/prettier/issues/6603",
        }
        for name, heading in (
            ("events.tsv", "timestamp_ns\tevent\tpoint\tparent\tchildren\tcheckpoint_id\tlatency_ns\n"),
            ("sandbox-ids.tsv", "role\tsandbox_id\tparent_id\tcreated_from\n"),
            ("segments.tsv", "rollout\tsegment\tsandbox_id\tmanifest_sha256\n"),
        ):
            (self.raw / name).write_text(heading)

    def record(self, filename: str, line: str) -> None:
        with (self.raw / filename).open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def phase(self, name: str) -> None:
        self.phase_file.write_text(name + "\n", encoding="utf-8")

    def sandbox_id(self, sandbox: object) -> str:
        return str(sandbox if self.args.system == "agentenv" else sandbox.id)

    async def init_trenv(self) -> None:
        from sandbox_sdk.sandbox import Sandbox
        import sandbox_sdk.sandbox.sandbox_connection as connection

        connection.ORCHESTRATOR_PORT = int(os.environ.get("ORCHESTRATOR_PORT", "15005"))

        def direct_url(self, port=None):
            if self._sandbox is None:
                raise RuntimeError("sandbox is not running")
            return f"{self._sandbox.private_ip}:{port or 49982}"

        connection.SandboxConnection.get_sbx_url = direct_url
        self.sdk = Sandbox

    async def start(self, role: str, *, template: str | None = None, parent: str = "") -> object:
        started = time.monotonic_ns()
        if self.args.system == "agentenv":
            start_args = (["aenv", "start", "--cold", self.image, "--detach", "--timeout", "3600",
                           "--cpu", "2", "--memory", "4096"] if template is None else
                          ["aenv", "start", template, "--detach", "--timeout", "3600"])
            ident = await asyncio.to_thread(shell, *start_args)
            sandbox: object = ident
            for attempt in range(60):
                try:
                    await asyncio.to_thread(shell, "aenv", "exec", ident, "true")
                    break
                except subprocess.CalledProcessError:
                    if attempt == 59:
                        raise
                    await asyncio.sleep(1)
            if template is None:
                await asyncio.to_thread(shell, "aenv", "upload", ident, str(WORKLOAD), "/workspace/mixfs-workload")
        else:
            sandbox = await self.sdk.create(template=template or self.base_template, target_addr="127.0.0.1", timeout=self.args.timeout)
            if template is not None:
                runtime_tmp = self.data_root / "templates" / template / "runtime-tmp.tar"
                if runtime_tmp.exists():
                    guest_archive = "/dev/shm/mixfs-checkpoint-tmp.tar"
                    await sandbox.filesystem.write_bytes(guest_archive, runtime_tmp.read_bytes(), timeout=self.args.timeout)
                    restore = await sandbox.simple_process.start(
                        f"tar --xattrs --acls --numeric-owner -C /tmp -xf {guest_archive} && rm -f {guest_archive}",
                        user="root")
                    await self.wait_guest(restore)
            if template is None:
                # The base DAX template predates this sampled trace. Put the
                # frozen manifests in its private upper; checkpoints inherit it.
                segments = sorted(WORKLOAD / "segments" / segment / "actions.tsv"
                                  for segment in {name for path in self.rollouts.values() for name in path})
                dirs = " ".join(f"/opt/mixfs/segments/{path.parent.name}" for path in segments)
                mkdir = await sandbox.simple_process.start(f"mkdir -p {dirs}", user="root")
                await self.wait_guest(mkdir)
                for path in segments:
                    await sandbox.filesystem.write_bytes(
                        f"/opt/mixfs/segments/{path.parent.name}/actions.tsv", path.read_bytes(), timeout=self.args.timeout)
        ident = self.sandbox_id(sandbox)
        self.live[ident] = sandbox
        if template is not None:
            self._templates[ident] = template
        if self.args.system == "trenvx":
            chosen = template or self.base_template
            manifest = self.data_root / "templates" / chosen / "checkpoint-layers.json"
            layers = json.loads(manifest.read_text()) if manifest.exists() else []
            self._layers[ident] = layers
            self._active_layer[ident] = None
        self.record("sandbox-ids.tsv", f"{role}\t{ident}\t{parent}\t{template or 'root'}")
        self.record("events.tsv", f"{time.time_ns()}\tstart\troot\t{parent}\t{ident}\t\t{time.monotonic_ns()-started}")
        return sandbox

    async def wait_guest(self, process) -> None:
        output = await process.wait(timeout=self.args.timeout)
        if output.exit_code != 0:
            raise RuntimeError(f"guest command failed ({output.exit_code}): {output.stderr}")

    def checkpoint_build_config(self, current: str, name: str, layers: list[Path]) -> str:
        """Build a template-manager config for a clean VM with DAX history."""
        source = (ROOT / "systems/trenvx/config.toml").read_text()
        source = source.replace(f'data_root = "/var/lib/trenvx-exp5-cow"', f'data_root = "{self.data_root}"')
        source = re.sub(r'(?m)^template_id = .*$', f'template_id = "{name}"', source, count=1)
        source = source.replace('rootfs_build_mode = "normal"',
                                'rootfs_build_mode = "clone-template"\n'
                                f'base_template_id = "{current}"\n'
                                f'dax_layer_paths = {json.dumps([str(path) for path in layers])}')
        start = source.index('[template."')
        source = source[:start] + f'[template."{name}"]\n'
        # template.toml is deliberately simple; retain all task-specific VM
        # settings while omitting the top-level template_id key.
        import tomllib
        template = tomllib.loads((self.data_root / "templates" / current / "template.toml").read_text())
        keys = (("vcpu", template["vcpu"]), ("mem_mb", template["mem_mb"]),
                ("disk_mb", template["disk_mb"]), ("rootfs_size", template["rootfs_size"]),
                ("kernel_version", template["kernel_version"]), ("docker_img", template["docker_img"]),
                ("no_pull", template["no_pull"]), ("huge_pages", template.get("huge_pages", False)),
                ("overlay", True), ("vmm_type", template["vmm_type"]))
        for key, value in keys:
            encoded = json.dumps(value)
            source += f'{key} = {encoded}\n'
        return source

    async def promote_snapshot(self, current: str, parent: str, name: str, runtime_tmp: Path) -> None:
        """Seal the parent's upper and build a clean template with DAX history."""
        source = self.data_root / "templates" / current
        final = self.data_root / "templates" / name
        if final.exists():
            raise RuntimeError("checkpoint template name already exists")
        upper = source / "instances" / parent / "writable-rootfs.ext4"
        inherited = sorted((source / "image").glob("checkpoint-*.ext4"))
        temp_root = Path(tempfile.mkdtemp(prefix="mixfs-exp5-checkpoint-", dir=self.data_root))
        upper_copy = temp_root / "upper.ext4"
        archive = temp_root / "upper.tar"
        layer = temp_root / "layer.ext4"
        config = temp_root / "template.toml"
        try:
            await asyncio.to_thread(shell, "cp", "--reflink=auto", "--sparse=always", str(upper), str(upper_copy))
            await asyncio.to_thread(archive_upper, upper_copy, archive)
            await asyncio.to_thread(build_layer, archive, layer)
            layers = [*inherited, layer]
            config.write_text(self.checkpoint_build_config(current, name, layers))
            manager = REPO / "baselines/TrEnv-X/packages/template-manager/bin/template-manager"
            self.templates.append(final)
            result = await asyncio.to_thread(subprocess.run, [str(manager), "--config", str(config)],
                                             text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            (self.raw / f"checkpoint-{self.counter}-template-manager.log").write_text(
                result.stdout + "\n--- stderr ---\n" + result.stderr)
            if result.returncode:
                raise RuntimeError(f"template-manager failed ({result.returncode}); see checkpoint-{self.counter}-template-manager.log")
            shutil.copy2(runtime_tmp, final / "runtime-tmp.tar")
            (final / "checkpoint-layers.json").write_text(json.dumps(
                [f"checkpoint-{index:04d}.ext4" for index in range(1, len(layers) + 1)]) + "\n")
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

    async def run_segment(self, sandbox: object, role: str, segment: str) -> None:
        ident = self.sandbox_id(sandbox)
        manifest = WORKLOAD / "segments" / segment / "actions.tsv"
        digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
        self.phase(f"tool:{segment}")
        guest_workload = "/workspace/mixfs-workload" if self.args.system == "agentenv" else "/opt/mixfs"
        guest_output = (f"/workspace/artifacts/exp5/{role}/{segment}" if self.args.system == "agentenv"
                        else f"/tmp/mixfs-exp5/{role}/{segment}")
        variables = {
            "ROUND": segment, "BRANCH": role, "SANDBOX_LABEL": role,
            "ACTIONS_ROOT": f"{guest_workload}/segments", "OUTPUT_DIR": guest_output,
            "ACTION_TIMEOUT_SECONDS": "600", "MEMORY_SAMPLE_INTERVAL_SECONDS": "0.1",
        }
        output = self.raw / "rollouts" / role / segment
        output.parent.mkdir(parents=True, exist_ok=True)
        if self.args.system == "agentenv":
            assignment = " ".join(f"{key}='{value}'" for key, value in variables.items())
            await asyncio.to_thread(shell, "aenv", "exec", ident, "bash", "-lc",
                                    f"{assignment} bash {guest_workload}/guest-runner.sh")
            await asyncio.to_thread(shell, "aenv", "download", ident, guest_output, str(output.parent))
            # `aenv download` uses the basename of the guest directory.
            if not (output / "steps.tsv").exists():
                raise RuntimeError(f"missing guest steps: {output}")
        else:
            output.mkdir()
            process = await sandbox.simple_process.start(f"/bin/bash {guest_workload}/guest-runner.sh", user="root", env_vars=variables)
            await self.wait_guest(process)
            archive_guest = f"/tmp/mixfs-exp5-{role}-{segment}.tar.gz"
            pack = await sandbox.simple_process.start(f"tar -C {guest_output} -czf {archive_guest} .", user="root")
            await self.wait_guest(pack)
            archive = output / "artifacts.tar.gz"
            archive.write_bytes(await sandbox.download_file(archive_guest, timeout=self.args.timeout))
            with tarfile.open(archive, "r:gz") as handle:
                handle.extractall(output, filter="data")
        self.record("segments.tsv", f"{role}\t{segment}\t{ident}\t{digest}")
        with (output / "steps.tsv").open(newline="") as handle:
            failed = [row for row in csv.DictReader(handle, delimiter="\t") if row["exit_code"] != "0"]
        # An agent may try a command that fails and then recover. The full
        # action sequence, including failures, is part of the sampled trace.
        if failed:
            self.record("agent-action-failures.tsv", f"{role}\t{segment}\t{json.dumps(failed)}")
        await self.physical_memory(f"after-{role}-{segment}")

    async def run_path(self, sandbox: object, role: str, segments: list[str]) -> None:
        for segment in segments:
            await self.run_segment(sandbox, role, segment)

    async def capture_template(self, sandbox: object, point: str) -> str:
        parent = self.sandbox_id(sandbox)
        started = time.monotonic_ns()
        self.counter += 1
        self.phase(f"checkpoint:{point}")
        current = self._template_of(parent)
        drop = await sandbox.simple_process.start(
            "grep -E '^(Cached|Buffers):' /proc/meminfo; sync; echo 3 > /proc/sys/vm/drop_caches; "
            "grep -E '^(Cached|Buffers):' /proc/meminfo", user="root")
        drop_result = await drop.wait(timeout=self.args.timeout)
        if drop_result.exit_code:
            raise RuntimeError(f"guest cache drop failed: {drop_result.stderr}")
        (self.raw / f"checkpoint-{self.counter}-cache-drop.txt").write_text(str(drop_result.stdout))
        runtime_guest = f"/dev/shm/mixfs-checkpoint-{self.counter}-tmp.tar"
        save_tmp = await sandbox.simple_process.start(
            "tar --xattrs --acls --numeric-owner "
            "--exclude='./mixfs-exp5*' --exclude='./mixfs-probe*' "
            f"-C /tmp -cf {runtime_guest} .", user="root")
        await self.wait_guest(save_tmp)
        runtime_tmp = self.raw / f"checkpoint-{self.counter}-runtime-tmp.tar"
        runtime_tmp.write_bytes(await sandbox.download_file(runtime_guest, timeout=self.args.timeout))
        clear_tmp = await sandbox.simple_process.start(f"rm -f {runtime_guest}", user="root")
        await self.wait_guest(clear_tmp)
        # Cloud Hypervisor's API socket is an AF_UNIX path. Keep runtime
        # template IDs short even when the human-readable run ID is long.
        run_key = hashlib.sha256(self.raw.name.encode()).hexdigest()[:12]
        template = f"exp5-dax-{run_key}-{self.counter}"
        await self.promote_snapshot(current, parent, template, runtime_tmp)
        self.record("events.tsv", f"{time.time_ns()}\tcheckpoint\t{point}\t{parent}\t\t{template}\t{time.monotonic_ns()-started}")
        return template

    async def capture_agentenv_template(self, sandbox: object, point: str) -> str:
        parent = self.sandbox_id(sandbox)
        started = time.monotonic_ns()
        output = await asyncio.to_thread(shell, "aenv", "snapshot", "create", parent)
        prefix = "Created snapshot "
        line = next((line for line in output.splitlines() if line.startswith(prefix)), None)
        if line is None:
            raise RuntimeError(f"missing snapshot ID: {output}")
        template = line[len(prefix):].strip()
        self.agentenv_templates.append(template)
        self.counter += 1
        self.record("events.tsv", f"{time.time_ns()}\tcheckpoint\t{point}\t{parent}\t\t{template}\t{time.monotonic_ns()-started}")
        return template

    async def checkpoint_and_resume(self, sandbox: object, point: str, role: str) -> tuple[str, object]:
        template = await self.capture_template(sandbox, point)
        parent = self.sandbox_id(sandbox)
        resumed = await self.start(role, template=template, parent=parent)
        await self.delete(sandbox)
        return template, resumed

    async def fork(self, sandbox: object, count: int, point: str, role: str, *, event: str = "fork") -> tuple[object, list[object]]:
        parent = self.sandbox_id(sandbox)
        started = time.monotonic_ns()
        self.phase(f"fork:{point}")
        if self.args.system == "agentenv":
            template = await self.capture_agentenv_template(sandbox, point)
            resumed = sandbox
        else:
            template, resumed = await self.checkpoint_and_resume(sandbox, point, role)
        children = await asyncio.gather(*(self.start(f"child@{point}", template=template, parent=parent) for _ in range(count)))
        ids = [self.sandbox_id(child) for child in children]
        self.record("events.tsv", f"{time.time_ns()}\t{event}\t{point}\t{parent}\t{','.join(ids)}\t{template}\t{time.monotonic_ns()-started}")
        return resumed, children

    async def delete(self, sandbox: object) -> None:
        ident = self.sandbox_id(sandbox)
        if self.args.system == "agentenv":
            await asyncio.to_thread(shell, "aenv", "delete", ident)
        else:
            await self.sdk.kill(ident, target_addr="127.0.0.1")
            await asyncio.sleep(1.5)
            await sandbox.close()
        self.live.pop(ident)

    def _template_of(self, ident: str) -> str:
        return self._templates.get(ident, self.base_template)

    async def do_grpo(self) -> None:
        sandboxes = await asyncio.gather(*(self.start(role) for role in ROLES))
        self.phase("root-ready")
        await asyncio.gather(*(self.run_path(sandbox, role, self.rollouts[role]) for sandbox, role in zip(sandboxes, ROLES, strict=True)))

    async def do_bpo(self) -> None:
        backbone_path = self.rollouts["backbone"]
        if len(backbone_path) != 5:
            raise RuntimeError("BPO backbone must have five segments")
        backbone = await self.start("backbone")
        await self.run_path(backbone, "backbone", backbone_path[:2])
        if self.args.system == "agentenv":
            early_template = await self.capture_agentenv_template(backbone, "save-after-backbone-2")
        else:
            early_template, backbone = await self.checkpoint_and_resume(backbone, "save-after-backbone-2", "backbone")
        await self.run_path(backbone, "backbone", backbone_path[2:4])
        if self.args.system == "agentenv":
            late_template = await self.capture_agentenv_template(backbone, "save-after-backbone-4")
        else:
            late_template, backbone = await self.checkpoint_and_resume(backbone, "save-after-backbone-4", "backbone")
        await self.run_path(backbone, "backbone", backbone_path[4:])
        early = await asyncio.gather(*(self.start("early-child", template=early_template, parent=self.sandbox_id(backbone)) for _ in range(3)))
        late = await asyncio.gather(*(self.start("late-child", template=late_template, parent=self.sandbox_id(backbone)) for _ in range(3)))
        self.record("events.tsv", f"{time.time_ns()}\tfork\texpand-after-backbone-2\t{self.sandbox_id(backbone)}\t{','.join(map(self.sandbox_id,early))}\t{early_template}\t0")
        self.record("events.tsv", f"{time.time_ns()}\tfork\texpand-after-backbone-4\t{self.sandbox_id(backbone)}\t{','.join(map(self.sandbox_id,late))}\t{late_template}\t0")
        jobs = [(sandbox, f"early_{index}", self.rollouts[f"early_{index}"][2:]) for index, sandbox in enumerate(early, 1)]
        jobs += [(sandbox, f"late_{index}", self.rollouts[f"late_{index}"][4:]) for index, sandbox in enumerate(late, 1)]
        await asyncio.gather(*(self.run_path(*job) for job in jobs))

    async def do_tvcache(self) -> None:
        async def replay_prefix_tree(sandbox: object, roles: list[str], offset: int) -> None:
            """Execute the rollout trie, snapshotting only at actual divergence points."""
            common: list[str] = []
            while all(offset + len(common) < len(self.rollouts[role]) for role in roles):
                candidate = self.rollouts[roles[0]][offset + len(common)]
                if any(self.rollouts[role][offset + len(common)] != candidate for role in roles[1:]):
                    break
                common.append(candidate)
            label_role = "backbone" if "backbone" in roles else roles[0]
            await self.run_path(sandbox, label_role, common)
            offset += len(common)
            if len(roles) == 1:
                if offset != len(self.rollouts[roles[0]]):
                    await self.run_path(sandbox, roles[0], self.rollouts[roles[0]][offset:])
                return
            if any(offset == len(self.rollouts[role]) for role in roles):
                raise RuntimeError(f"a rollout is a strict prefix at offset {offset}: {roles}")
            groups: dict[str, list[str]] = {}
            for role in roles:
                groups.setdefault(self.rollouts[role][offset], []).append(role)
            if len(groups) < 2:
                raise RuntimeError(f"failed to find TVCache divergence at offset {offset}: {roles}")
            ordered = list(groups.values())
            primary_index = next((index for index, group in enumerate(ordered) if "backbone" in group), 0)
            primary = ordered.pop(primary_index)
            point = f"longest-prefix-{label_role}-{offset}"
            sandbox, children = await self.fork(sandbox, len(ordered), point, label_role)
            jobs = [(sandbox, primary, offset)]
            jobs.extend((child, group, offset) for child, group in zip(children, ordered, strict=True))
            # Physical-memory probes scan every live VM.  Advance trie
            # subtrees deterministically so a sibling cannot add VMs or take
            # a snapshot while that global probe is iterating.
            for job in jobs:
                await replay_prefix_tree(*job)

        root = await self.start("backbone")
        await replay_prefix_tree(root, list(ROLES), 0)

    async def mappings(self, phase: str) -> None:
        await asyncio.to_thread(shell, str(REPO / "motivation/experiments/lib/host-vmm-mapping-snapshot.sh"),
                                str(self.raw / "host/mapping-snapshots.tsv"), phase, str(self.args.cgroup),
                                "firecracker" if self.args.system == "agentenv" else "cloud-hyperviso*", "32768")

    async def physical_memory(self, label: str) -> None:
        async with self.physical_sample_lock:
            await self._physical_memory(label)

    async def _physical_memory(self, label: str) -> None:
        self.physical_sample_count += 1
        sample = self.raw / "host/physical-samples" / f"{self.physical_sample_count:03d}-{label}"
        probes = sample / "probes"
        probes.mkdir(parents=True)
        subprocesses: list[subprocess.Popen] = []
        guest_processes: list[object] = []
        trenv_script = WORKLOAD / "physical-cache-probe.py"
        try:
            for ident, sandbox in self.live.items():
                script = "/workspace/mixfs-workload/physical-cache-probe.py"
                if self.args.system == "agentenv":
                    stderr = (probes / f"{ident}.stderr.log").open("wb")
                    process = subprocess.Popen(["aenv", "exec", ident, "python3", script, ident],
                                               stdout=subprocess.DEVNULL, stderr=stderr)
                    stderr.close()
                    subprocesses.append(process)
                else:
                    clear = await sandbox.simple_process.start(f"rm -rf /dev/shm/mixfs-exp5-{ident}", user="root")
                    await self.wait_guest(clear)
                    await sandbox.filesystem.write_bytes(f"/dev/shm/mixfs-probe-{ident}.py", trenv_script.read_bytes(),
                                                         timeout=self.args.timeout)
                    guest_processes.append(await sandbox.simple_process.start(
                        f"python3 /dev/shm/mixfs-probe-{ident}.py {ident}", user="root"))
            for attempt in range(120):
                ready = True
                for ident, sandbox in self.live.items():
                    marker = f"/dev/shm/mixfs-exp5-{ident}/marker.json"
                    try:
                        if self.args.system == "agentenv":
                            await asyncio.to_thread(shell, "aenv", "exec", ident, "test", "-s", marker)
                        else:
                            check = await sandbox.simple_process.start(f"test -s {marker}", user="root")
                            await self.wait_guest(check)
                    except Exception:
                        ready = False
                        break
                if ready:
                    break
                await asyncio.sleep(0.25)
            else:
                raise RuntimeError("guest physical-cache probes not ready")
            for ident, sandbox in self.live.items():
                directory = probes / ident
                guest_dir = f"/dev/shm/mixfs-exp5-{ident}"
                if self.args.system == "agentenv":
                    await asyncio.to_thread(shell, "aenv", "download", ident, guest_dir, str(probes))
                    downloaded = probes / f"mixfs-exp5-{ident}"
                    downloaded.rename(directory)
                else:
                    directory.mkdir()
                    for name in ("marker.json", "file-pfns.bin"):
                        (directory / name).write_bytes(await sandbox.download_file(f"{guest_dir}/{name}", timeout=self.args.timeout))
                if not (directory / "file-pfns.bin").exists():
                    raise RuntimeError(f"missing physical-cache probe from {ident}")
            result_path = sample / "physical-memory.json"
            await asyncio.to_thread(shell, "sudo", "-n", "python3", str(ROOT / "physical_cache.py"),
                                    str(self.raw), str(len(self.live)), str(probes), str(result_path))
            if label == "terminal-retained":
                shutil.copy2(result_path, self.raw / "host/physical-memory.json")
        finally:
            for process in subprocesses:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            for process in guest_processes:
                try:
                    await process.kill(timeout=10)
                except Exception:
                    pass
            for ident, sandbox in self.live.items():
                try:
                    if self.args.system == "agentenv":
                        await asyncio.to_thread(shell, "aenv", "exec", ident, "rm", "-rf",
                                                f"/dev/shm/mixfs-exp5-{ident}")
                    else:
                        clear = await sandbox.simple_process.start(
                            f"rm -rf /dev/shm/mixfs-exp5-{ident} /dev/shm/mixfs-probe-{ident}.py", user="root")
                        await self.wait_guest(clear)
                except Exception:
                    pass

    async def run(self) -> None:
        self._templates: dict[str, str] = {}
        if self.args.system == "trenvx":
            await self.init_trenv()
        trace_hash = hashlib.sha256()
        trace_hash.update((WORKLOAD / "rollouts.json").read_bytes())
        referenced_segments = {segment for path in self.rollouts.values() for segment in path}
        for manifest in sorted(WORKLOAD / "segments" / segment / "actions.tsv" for segment in referenced_segments):
            trace_hash.update(manifest.parent.name.encode() + b"\0" + manifest.read_bytes())
        (self.raw / "metadata.json").write_text(json.dumps({
            "system": self.args.system, "scenario": self.args.scenario,
            "workload_name": WORKLOAD_NAME, "task": self.task,
            "agentenv_balloon_mode": os.environ.get("AGENTENV_BALLOON_MODE") if self.args.system == "agentenv" else None,
            "trace_sha256": trace_hash.hexdigest(),
            "agent_sampling_sha256": hashlib.sha256((WORKLOAD / "agent-sampling.json").read_bytes()).hexdigest(),
            "tool_time_only": True, "guest_memory_mib": 4096, "guest_vcpus": 2,
            "cache_policy": ("drop-parent-guest-cache-before-direct-memory-snapshot" if self.args.system == "trenvx"
                             else "natural-no-drop-caches"),
            "trace_kind": "deepseek-agent-sampled-code-repair-replay",
            "dax_rootfs_template_policy": "base-rootfs-hardlink" if self.args.system == "trenvx" else "not-applicable",
            "checkpoint_dax_policy": "seal-upper-as-immutable-inherited-dax-layer" if self.args.system == "trenvx" else "agentenv-persistent-snapshot-cow",
            "vm_memory_checkpoint_policy": "clean-template-snapshot-after-dax-seal" if self.args.system == "trenvx" else "persistent-memory-snapshot",
            "writable_image_policy": "fresh-independent-upper" if self.args.system == "trenvx" else "overlaybd-runtime-upper",
            "host_cow_backend": "btrfs-shared-dax-independent-upper" if self.args.system == "trenvx" else "agentenv-native",
            "physical_cache_method": "guest-file-pfn-to-host-pfn-dedup-plus-dax-pss",
            "peak_sampling_policy": "after-each-segment-plus-terminal",
            "bpo_schedule": "backbone-first-online-saved-states" if self.args.scenario == "bpo" else "not-applicable",
        }, indent=2) + "\n")
        try:
            self.phase("setup")
            await getattr(self, f"do_{self.args.scenario}")()
            if len(self.live) != 7:
                raise RuntimeError(f"expected 7 live terminal sandboxes, got {len(self.live)}")
            self.phase("terminal-retained")
            await asyncio.sleep(self.args.settle_seconds)
            await self.mappings("terminal-retained")
            await self.physical_memory("terminal-retained")
            self.phase("done")
        finally:
            self.phase("cleanup")
            if self.args.system == "agentenv":
                for ident in reversed(list(self.live)):
                    subprocess.run(["aenv", "delete", ident], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                for template in reversed(self.agentenv_templates):
                    try:
                        await asyncio.to_thread(shell, "aenv", "template", "delete", template)
                    except Exception as error:
                        self.record("cleanup-errors.log", f"delete template {template}: {error}")
            else:
                for ident, sandbox in reversed(list(self.live.items())):
                    try:
                        await self.sdk.kill(ident, target_addr="127.0.0.1")
                        await asyncio.sleep(1.5)
                    except Exception as error:
                        self.record("cleanup-errors.log", f"kill {ident}: {error}")
                    finally:
                        try:
                            await sandbox.close()
                        except Exception as error:
                            self.record("cleanup-errors.log", f"close {ident}: {error}")
                for path in reversed(self.templates):
                    shutil.rmtree(path, ignore_errors=True)
            self.phase_file.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--system", choices=("agentenv", "trenvx"), required=True)
    parser.add_argument("--scenario", choices=("grpo", "bpo", "tvcache"), required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--cgroup", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=3600)
    parser.add_argument("--settle-seconds", type=float, default=3)
    asyncio.run(Controller(parser.parse_args()).run())


if __name__ == "__main__":
    main()
