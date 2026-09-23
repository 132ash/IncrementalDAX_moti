#!/usr/bin/env python3
from __future__ import annotations

import csv
import statistics
import sys
from pathlib import Path


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def num(row: dict[str, str], key: str) -> float:
    try:
        return float(row.get(key, 0))
    except ValueError:
        return 0


def env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def metrics(run: Path) -> dict[str, float]:
    steps = rows(run / "replay/steps.tsv")
    guest = rows(run / "replay/guest-memory.tsv")
    host = rows(run / "host/memory-samples.tsv")
    active_guest = [r for r in guest if r["phase"] in {"before", "running", "after"}]
    active_host = [r for r in host if r["phase"] == "running"] or host
    durations = [num(r, "duration_ns") / 1_000_000 for r in steps]
    vmm_key = "vmm_rss_kib" if "vmm_rss_kib" in host[0] else "firecracker_rss_kib"
    return {
        "cold_start_ms": int((run / "cold-start-duration-ns.txt").read_text()) / 1_000_000,
        "total_ms": sum(durations),
        "p50_ms": statistics.median(durations),
        "p95_ms": sorted(durations)[max(0, int(len(durations) * 0.95) - 1)],
        "guest_peak_mib": max(
            (num(r, "MemTotal_kib") - num(r, "MemAvailable_kib")) / 1024
            for r in active_guest
        ),
        "host_peak_mib": max(num(r, "cgroup_current_bytes") for r in active_host) / 1048576,
        "vmm_peak_rss_mib": max(num(r, vmm_key) for r in active_host) / 1024,
    }


def main() -> None:
    output = Path(sys.argv[1]).resolve()
    agentenv = Path(sys.argv[2]).resolve()
    run_id = (output / "latest-run.txt").read_text().strip()
    run = output / "raw" / run_id
    current = metrics(run)
    agent_id = (agentenv / "latest-run.txt").read_text().strip()
    baseline = metrics(agentenv / "raw" / agent_id)
    current_meta = env(run / "metadata.env")
    baseline_meta = env(agentenv / "raw" / agent_id / "metadata.env")
    manifest_equal = (
        current_meta.get("action_manifest_sha256")
        == baseline_meta.get("action_manifest_sha256")
    )
    steps = rows(run / "replay/steps.tsv")
    cmd_rows = []
    for line in (run / "replay/actions.tsv").read_text().splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3:
            cmd_rows.append((parts[0], parts[2].split(maxsplit=1)[0].lstrip("(")))
    tools = dict(cmd_rows)
    action_lines = ["| action | tool | duration (ms) | exit |", "| ---: | --- | ---: | ---: |"]
    for row in steps:
        action_lines.append(
            f"| {row['step']} | `{tools.get(row['step'], 'action')}` | "
            f"{num(row, 'duration_ns') / 1_000_000:.3f} | {row['exit_code']} |"
        )
    comparison = []
    for name, data in [("AgentENV cold/FC + OverlayBD direct I/O", baseline), ("TrEnv-X restore/custom CH + pmem/DAX", current)]:
        comparison.append(
            f"| {name} | {data['cold_start_ms']:.1f} | {data['total_ms']:.1f} | {data['p50_ms']:.1f} | "
            f"{data['p95_ms']:.1f} | {data['guest_peak_mib']:.1f} | "
            f"{data['host_peak_mib']:.1f} | {data['vmm_peak_rss_mib']:.1f} |"
        )
    oracle_ok = (run / "oracle-exit-code.txt").read_text().strip() == "0"
    dax_ok = (
        "root=/dev/pmem0" in (run / "replay/proc-cmdline.txt").read_text()
        and "/dev/pmem0" in (run / "replay/findmnt.txt").read_text()
        and "dax=always" in (run / "replay/findmnt.txt").read_text()
    )
    status = "通过" if oracle_ok and dax_ok else "未通过"
    start_reduction = (1 - current["cold_start_ms"] / baseline["cold_start_ms"]) * 100
    action_reduction = (1 - current["total_ms"] / baseline["total_ms"]) * 100
    guest_reduction = (1 - current["guest_peak_mib"] / baseline["guest_peak_mib"]) * 100
    text = f"""# Prettier #14400：TrEnv-X 与 AgentENV 对比

最新 TrEnv-X 运行：`{run_id}`；对照 AgentENV 运行：`{agent_id}`。

## 核心结果

| runtime | create API (ms) | 26 actions total (ms) | action p50 (ms) | action p95 (ms) | guest peak (MiB) | runtime cgroup peak (MiB) | VMM peak RSS (MiB) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(comparison)}

TrEnv-X 本轮正确性和 pmem/DAX 验收：**{status}**；两侧 action manifest digest 一致：**{'是' if manifest_equal else '否'}**。两行 host cgroup 口径不同：TrEnv-X 是单 sandbox cgroup，AgentENV 是整个 server 容器 cgroup；因此可直接比较 action/guest 数据，host cgroup 数值只作诊断，不能解释为严格的逐 sandbox 差值。

在这一轮中，TrEnv-X 的 create API、26-action 总时间和 guest peak 分别低 **{start_reduction:.1f}%**、**{action_reduction:.1f}%** 和 **{guest_reduction:.1f}%**。第一列实际比较 AgentENV OCI cold start 与 TrEnv-X snapshot restore，并非同类 restore；整张表也是单次端到端管线结果，差异同时包含 VMM、rootfs、snapshot 和 I/O 路径，不能单独归因于 DAX。

Guest page cache、匿名页、kernel/other 分桶，以及启动和 action 差异的证据分析见 [`analysis.md`](analysis.md)。

## 逐 action 延迟

{chr(10).join(action_lines)}

## 复现信息

原始数据、stdout/stderr、patch、guest 内存/vmstat、host per-sandbox cgroup 采样、VMM RSS/PSS、内核命令行和 mount 拓扑位于 [`raw/{run_id}/`](raw/{run_id}/)。这是一轮管线验证；性能结论应至少做 10 次交错重复并报告方差。
"""
    (output / "summary.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
