#!/usr/bin/env python3
"""Rebuild the human-readable summary and SVG figures from immutable raw runs."""

from __future__ import annotations

import csv
import html
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Run:
    run_id: str
    root: Path
    steps: list[dict[str, str]]
    guest: list[dict[str, str]]
    host: list[dict[str, str]]
    commands: dict[str, str]
    oracle_ok: bool
    cleanup_ok: bool


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def load_runs(output: Path) -> list[Run]:
    runs: list[Run] = []
    for root in sorted((output / "raw").glob("*")):
        replay = root / "replay"
        required = [replay / "steps.tsv", replay / "guest-memory.tsv", root / "host/memory-samples.tsv"]
        if not all(path.is_file() for path in required):
            continue
        commands: dict[str, str] = {}
        for row in read_tsv(replay / "actions.tsv"):
            command = row.get("command", "")
            if not command:
                # The historical manifest has no header.
                continue
            commands[row.get("step", "")] = command
        if not commands:
            with (replay / "actions.tsv").open(encoding="utf-8") as handle:
                for line in handle:
                    parts = line.rstrip("\n").split("\t", 2)
                    if len(parts) == 3:
                        commands[parts[0]] = parts[2]
        cleanup_text = (root / "cleanup.log").read_text(encoding="utf-8") if (root / "cleanup.log").exists() else ""
        runs.append(
            Run(
                root.name,
                root,
                read_tsv(replay / "steps.tsv"),
                read_tsv(replay / "guest-memory.tsv"),
                read_tsv(root / "host/memory-samples.tsv"),
                commands,
                (root / "oracle-exit-code.txt").read_text().strip() == "0",
                "deleted=" in cleanup_text,
            )
        )
    return runs


def number(row: dict[str, str], key: str) -> float:
    try:
        return float(row.get(key, 0))
    except ValueError:
        return 0.0


def guest_metrics(row: dict[str, str]) -> dict[str, float]:
    total = number(row, "MemTotal_kib")
    available = number(row, "MemAvailable_kib")
    page_cache = (
        number(row, "Cached_kib")
        + number(row, "Buffers_kib")
        + number(row, "SReclaimable_kib")
        - number(row, "Shmem_kib")
    )
    kernel = (
        number(row, "SUnreclaim_kib")
        + number(row, "KernelStack_kib")
        + number(row, "PageTables_kib")
        + number(row, "Percpu_kib")
    )
    return {
        "working_set": max(total - available, 0),
        "anon": number(row, "AnonPages_kib"),
        "page_cache": max(page_cache, 0),
        "kernel": kernel,
    }


def mib(kib: float) -> float:
    return kib / 1024


def svg_bar_chart(path: Path, title: str, labels: list[str], values: list[float], ylabel: str) -> None:
    width, height = 1080, 430
    left, right, top, bottom = 72, 24, 54, 105
    chart_w, chart_h = width - left - right, height - top - bottom
    maximum = max(values, default=1) or 1
    bar_w = chart_w / max(len(values), 1)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<style>text{font-family:system-ui,sans-serif;fill:#24292f}.title{font-size:20px;font-weight:600}.tick{font-size:11px}.label{font-size:10px}</style>',
        f'<text class="title" x="{left}" y="30">{html.escape(title)}</text>',
    ]
    for tick in range(5):
        value = maximum * tick / 4
        y = top + chart_h - chart_h * tick / 4
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="#d8dee4"/>')
        parts.append(f'<text class="tick" x="{left-8}" y="{y+4:.1f}" text-anchor="end">{value:.0f}</text>')
    for index, (label, value) in enumerate(zip(labels, values)):
        x = left + index * bar_w + bar_w * 0.14
        h = chart_h * value / maximum
        y = top + chart_h - h
        color = "#d1242f" if value == maximum else "#2f81f7"
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w*0.72:.1f}" height="{h:.1f}" fill="{color}"/>')
        parts.append(f'<text class="label" transform="translate({x+bar_w*0.36:.1f},{top+chart_h+10}) rotate(55)" text-anchor="start">{html.escape(label)}</text>')
    parts.append(f'<text class="tick" transform="translate(17,{top+chart_h/2:.1f}) rotate(-90)" text-anchor="middle">{html.escape(ylabel)}</text>')
    parts.append('</svg>')
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def svg_grouped_chart(path: Path, title: str, groups: list[tuple[str, dict[str, float]]]) -> None:
    keys = ["working_set", "anon", "page_cache", "kernel"]
    names = {"working_set": "working set", "anon": "anonymous", "page_cache": "page cache", "kernel": "kernel"}
    colors = {"working_set": "#8250df", "anon": "#2f81f7", "page_cache": "#2da44e", "kernel": "#bf8700"}
    width, height = 1000, 460
    left, right, top, bottom = 78, 30, 70, 90
    chart_w, chart_h = width-left-right, height-top-bottom
    maximum = max((v for _, values in groups for v in values.values()), default=1) or 1
    group_w = chart_w / max(len(groups), 1)
    bar_w = group_w / 5
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">', '<rect width="100%" height="100%" fill="white"/>', '<style>text{font-family:system-ui,sans-serif;fill:#24292f}.title{font-size:20px;font-weight:600}.tick{font-size:11px}.label{font-size:12px}</style>', f'<text class="title" x="{left}" y="30">{html.escape(title)}</text>']
    for tick in range(5):
        value = maximum*tick/4; y = top+chart_h-chart_h*tick/4
        parts += [f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="#d8dee4"/>', f'<text class="tick" x="{left-8}" y="{y+4:.1f}" text-anchor="end">{value:.0f}</text>']
    for gi, (label, values) in enumerate(groups):
        gx = left + gi*group_w
        for ki, key in enumerate(keys):
            value = values.get(key, 0); h = chart_h*value/maximum; x = gx+bar_w*(ki+0.5); y = top+chart_h-h
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w*0.8:.1f}" height="{h:.1f}" fill="{colors[key]}"/>')
        parts.append(f'<text class="label" x="{gx+group_w/2:.1f}" y="{top+chart_h+24}" text-anchor="middle">{html.escape(label)}</text>')
    legend_x = left
    for key in keys:
        parts += [f'<rect x="{legend_x}" y="45" width="12" height="12" fill="{colors[key]}"/>', f'<text class="tick" x="{legend_x+17}" y="56">{names[key]}</text>']
        legend_x += 145
    parts.append(f'<text class="tick" transform="translate(18,{top+chart_h/2:.1f}) rotate(-90)" text-anchor="middle">MiB</text>')
    parts.append('</svg>')
    path.write_text("\n".join(parts)+"\n", encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} OUTPUT_ROOT")
    output = Path(sys.argv[1]).resolve()
    figures = output / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    runs = load_runs(output)
    if not runs:
        raise SystemExit(f"no complete raw runs under {output / 'raw'}")
    latest_id_path = output / "latest-run.txt"
    latest_id = latest_id_path.read_text(encoding="utf-8").strip() if latest_id_path.exists() else runs[-1].run_id
    latest = next((run for run in runs if run.run_id == latest_id), runs[-1])

    durations_ms = [number(row, "duration_ns") / 1_000_000 for row in latest.steps]
    labels = []
    for row in latest.steps:
        step = row["step"]
        command = latest.commands.get(step, "action").strip().split(maxsplit=1)[0].lstrip("(")
        labels.append(f"{step}:{command}")
    svg_bar_chart(figures / "latency-by-action.svg", f"Prettier-14400 action latency ({latest.run_id})", labels, durations_ms, "milliseconds")

    guest_baseline_rows = [row for row in latest.guest if row.get("phase") == "baseline"]
    guest_running_rows = [row for row in latest.guest if row.get("phase") in {"before", "running", "after"}]
    baseline = guest_metrics(guest_baseline_rows[-1])
    peak_row = max(guest_running_rows, key=lambda row: guest_metrics(row)["working_set"])
    peak = guest_metrics(peak_row)
    guest_groups = [("guest idle", {key: mib(value) for key, value in baseline.items()}), (f"guest peak (step {peak_row['step']})", {key: mib(value) for key, value in peak.items()})]

    host_idle = [row for row in latest.host if row.get("phase") == "idle"]
    host_running = [row for row in latest.host if row.get("phase") == "running"]
    host_base = host_idle[-1] if host_idle else latest.host[0]
    host_peak = max(host_running or latest.host, key=lambda row: number(row, "cgroup_current_bytes"))
    host_groups = {
        "working_set": number(host_base, "cgroup_current_bytes") / 1048576,
        "anon": number(host_base, "cgroup_anon_bytes") / 1048576,
        "page_cache": number(host_base, "cgroup_file_bytes") / 1048576,
        "kernel": number(host_base, "cgroup_kernel_bytes") / 1048576,
    }
    host_peak_groups = {
        "working_set": number(host_peak, "cgroup_current_bytes") / 1048576,
        "anon": number(host_peak, "cgroup_anon_bytes") / 1048576,
        "page_cache": number(host_peak, "cgroup_file_bytes") / 1048576,
        "kernel": number(host_peak, "cgroup_kernel_bytes") / 1048576,
    }
    svg_grouped_chart(figures / "memory-breakdown.svg", f"Memory footprint and breakdown ({latest.run_id})", guest_groups + [("AgentENV cgroup idle", host_groups), ("AgentENV cgroup peak", host_peak_groups)])

    nonzero = [(row["step"], row["exit_code"]) for row in latest.steps if row["exit_code"] != "0"]
    patch_text = (latest.root / "replay/patch.diff").read_text(encoding="utf-8")
    patch_indent_ok = (
        '+      node.fullName === "svg:script" ||' in patch_text
        and '+      node.fullName === "svg:style" ||' in patch_text
    )
    cold_ms = int((latest.root / "cold-start-duration-ns.txt").read_text().strip()) / 1_000_000
    total_ms = sum(durations_ms)
    firecracker_base = number(host_base, "firecracker_rss_kib") / 1024
    firecracker_peak = max(number(row, "firecracker_rss_kib") for row in (host_running or latest.host)) / 1024
    metadata = read_env(latest.root / "metadata.env")
    comparison_rows = []
    for run in runs:
        run_metadata = read_env(run.root / "metadata.env")
        engine = run_metadata.get("overlaybd_io_engine")
        mode = "direct (2)" if engine == "2" else ("buffered (0)" if engine == "0" else "buffered (0)*")
        run_durations = [number(row, "duration_ns") / 1_000_000 for row in run.steps]
        run_guest = [row for row in run.guest if row.get("phase") in {"before", "running", "after"}]
        run_peak = max(guest_metrics(row)["working_set"] for row in run_guest)
        run_host = [row for row in run.host if row.get("phase") == "running"] or run.host
        run_cgroup_peak = max(number(row, "cgroup_current_bytes") for row in run_host) / 1048576
        comparison_rows.append(
            f"| `{run.run_id}` | {mode} | {sum(run_durations):.1f} | {statistics.median(run_durations):.3f} | {mib(run_peak):.1f} | {run_cgroup_peak:.1f} | {'通过' if run.oracle_ok else '失败'} |"
        )
    rows = []
    for row, label in zip(latest.steps, labels):
        rows.append(f"| {row['step']} | `{label.split(':', 1)[1]}` | {float(row['duration_ns'])/1e6:.3f} | {row['exit_code']} |")
    report = f"""# AgentENV / prettier-14400 实验结果

更新时间：{datetime.now(timezone.utc).isoformat(timespec='seconds')}。完整 raw runs：{len(runs)}；下列明细对应最新运行 `{latest.run_id}`。

## Summary

- 固定输入：26-action Tracebench replay；镜像 `{metadata.get('workload_image', 'unknown')}`。
- OverlayBD I/O 模式：`ioEngine={metadata.get('overlaybd_io_engine', '未记录')}`（`2` 表示本地只读 lower commit 使用 `O_DIRECT`）。
- sandbox 配额：{metadata.get('sandbox_cpu', '?')} vCPU / {metadata.get('sandbox_memory_mib', '?')} MiB；冷启动 {cold_ms:.1f} ms（不计入 workload）。
- 26 个 action 总 wall time {total_ms:.1f} ms，均值 {statistics.mean(durations_ms):.3f} ms，中位数 {statistics.median(durations_ms):.3f} ms，最慢 action {latest.steps[durations_ms.index(max(durations_ms))]['step']} 为 {max(durations_ms):.3f} ms。
- 非零 action：{', '.join(f'{step}={code}' for step, code in nonzero) or '无'}。原轨迹中的 008（镜像无 `rg`）和 016（无 `applypatch`）允许失败，runner 仍继续重放 observation-driven 修复路径。
- task-specific oracle：{'通过' if latest.oracle_ok else '失败'}；sandbox 清理：{'已确认删除' if latest.cleanup_ok else '尚未在 raw 日志中确认'}。
- patch 人工复核提示：{'新增行缩进符合周边代码' if patch_indent_ok else '功能修复存在，但新增 `svg:script`/`svg:style` 行缩进偏深；本次只证明 oracle 行为，不视为可直接提交的补丁'}。
- guest idle working-set 估算 {mib(baseline['working_set']):.1f} MiB，workload 峰值 {mib(peak['working_set']):.1f} MiB（step {peak_row['step']}）；峰值 page cache {mib(peak['page_cache']):.1f} MiB、匿名页 {mib(peak['anon']):.1f} MiB。
- host 上 AgentENV 容器 cgroup idle/峰值 memory.current 为 {host_groups['working_set']:.1f}/{host_peak_groups['working_set']:.1f} MiB；活跃 Firecracker RSS idle/峰值为 {firecracker_base:.1f}/{firecracker_peak:.1f} MiB。

![逐 action 延迟](figures/latency-by-action.svg)

![内存 breakdown](figures/memory-breakdown.svg)

## 运行对照

| run | OverlayBD mode | action total (ms) | median (ms) | guest peak (MiB) | AgentENV cgroup peak (MiB) | oracle |
| --- | --- | ---: | ---: | ---: | ---: | --- |
{chr(10).join(comparison_rows)}

`*` 第一轮 runner 尚未写入 `ioEngine`，但开启 Direct I/O 前对实际生成配置的检查值为 0。
两轮之间为了让 ublk daemon 重新加载配置重启过 Docker 容器；重启会解除旧 cgroup 对
host page cache 的记账。因此 cgroup memory 的两行不能作为严格的 buffered/direct
节省量对比，尤其不能把数 GiB 差值全部归因于 `O_DIRECT`。

## 逐工具/action 延迟

| action | 主工具 | duration (ms) | exit |
| ---: | --- | ---: | ---: |
{chr(10).join(rows)}

## 内存口径

- guest `working set = MemTotal - MemAvailable`，表示内核估算的当前不可立即回收占用；它不是 4096 MiB 配额，也不等于进程 RSS。
- guest `page cache = Cached + Buffers + SReclaimable - Shmem`；`anonymous = AnonPages`；`kernel = SUnreclaim + KernelStack + PageTables + Percpu`。这些是并列诊断项，不应相加后当成严格互斥总量。
- `guest idle` 在 action 前、可选 `drop_caches` 后采样，代表本次 VM/项目运行时基础内存；每个 action 有 before/20ms sampling/after 记录，极短 action 的瞬时尖峰仍可能漏采。
- host `AgentENV cgroup` 包含 server、ublk daemon、warm-pool Firecracker 和本次 sandbox。由于 AgentENV 当前没有 per-sandbox host cgroup，`file`（host page cache）只能在服务粒度报告；实验要求运行前没有其他 active sandbox 来减少归因歧义。
- Firecracker RSS/PSS 来自 host `/proc/<pid>/smaps_rollup`，采样器选择 RSS 最大的活跃 Firecracker；它不包含独立 ublk daemon 的 page cache。

### 为什么旧运行的 AgentENV cgroup 是几 GB

开启 Direct I/O 前的现场值为：`memory.current=5,655,949,312` bytes，其中
`file=5,405,487,104`、`anon=53,432,320`、`kernel=189,259,776` bytes；同时容器内
`/workspace/env/image-cache/commits` 的磁盘文件总量约为 5.1 GiB。这说明几 GB 主要是
AgentENV 在该 Docker cgroup 中读取/转换 OverlayBD commit 后形成的 **host file page
cache 记账**，不是单个 Firecracker/sandbox 的匿名内存。第一轮的 Firecracker RSS
峰值只有约 494.8 MiB，也支持这一判断。

Docker cgroup 的 file cache 是可回收的，且会在容器重启后解除原 cgroup 的记账；它既
不等于常驻、不可回收内存，也不能完全归属于某一个 sandbox。Direct-I/O 运行期间 host
cgroup file 峰值仅约 12.6 MiB，但因切换模式必须重启 daemon/container，这个数值同时
受到 `O_DIRECT` 和 cgroup 重新记账两个因素影响。

## 正确性与可复现性

oracle 检查 action 024 的 Prettier 输出是否把 SVG `<script>` 中两条关键 JavaScript 语句展开到预期缩进。`replay/patch.diff`、全部 stdout/stderr、guest/host 原始采样、镜像 digest、action manifest digest 和清理日志均保存在 [`raw/{latest.run_id}/`](raw/{latest.run_id}/)。

本结果是单次 AgentENV block baseline 的功能与测量管线验证，不能据此宣称 block 与 DAX 的性能差异。正式比较应做多次独立重复，并在相同 cache policy、CPU/内存配额和固定 action manifest 下报告方差。
"""
    (output / "summary.md").write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
