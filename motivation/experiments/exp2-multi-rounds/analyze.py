#!/usr/bin/env python3
from __future__ import annotations

import csv
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def number(row: dict[str, str], key: str) -> int:
    return int(row[key])


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} OUTPUT_ROOT")
    output = Path(sys.argv[1]).resolve()
    run_id = (output / "latest-run.txt").read_text().strip()
    run = output / "raw" / run_id
    step_rows: list[dict[str, str]] = []
    for round_no in range(1, 5):
        step_rows.extend(rows(run / "rounds" / str(round_no) / "steps.tsv"))
    durations = [int(row["duration_ns"]) / 1_000_000 for row in step_rows]
    by_round = {
        round_no: [int(row["duration_ns"]) / 1_000_000 for row in step_rows if int(row["round"]) == round_no]
        for round_no in range(1, 5)
    }
    memory_lines: list[str] = []
    for round_no in range(1, 5):
        samples = rows(run / "rounds" / str(round_no) / "guest-memory.tsv")
        baseline = next(row for row in samples if row["phase"] == "baseline")
        used = number(baseline, "MemTotal_kib") - number(baseline, "MemFree_kib")
        page_cache = max(
            number(baseline, "Cached_kib")
            + number(baseline, "Buffers_kib")
            - number(baseline, "Shmem_kib"),
            0,
        )
        memory_lines.append(
            f"| {round_no} | {used / 1024:.1f} | {page_cache / 1024:.1f} |"
        )
    host_pmem_path = run / "host-pmem.tsv"
    host_pmem_section = ""
    if host_pmem_path.exists():
        host_pmem_rows = rows(host_pmem_path)
        host_pmem_lines = "\n".join(
            f"| {row['round']} | {int(row['mapping_bytes']) / 1024 / 1024:.1f} |"
            for row in host_pmem_rows
        )
        host_pmem_section = f"""

## Host virtio-pmem rootfs mapping（TrEnv-X）

| round | host pmem mapping capacity (MiB) |
| ---: | ---: |
{host_pmem_lines}

这是 host 上作为 `/dev/pmem0` 暴露给 guest 的只读 rootfs 文件映射容量。它独立于 guest
RAM，不包含在上表的 `guest used` 或 `page cache` 中；容量也不是运行时 host RSS。
"""
    failures = [f"r{r['round']}/{r['step']}={r['exit_code']}" for r in step_rows if r["exit_code"] != "0"]
    oracle_path = run / "oracle-exit-code.txt"
    oracle_ok = oracle_path.exists() and oracle_path.read_text().strip() == "0"
    transitions = rows(run / "transitions.tsv")
    transition_lines = "\n".join(
        f"| {r['after_round']} | {r['checkpoint_ns']} | {r['restore_ns']} | {r.get('image_rebuild_ns', '0')} |"
        for r in transitions
    )
    round_lines = "\n".join(
        f"| {n} | {len(values)} | {sum(values):.3f} | {statistics.median(values):.3f} | {max(values):.3f} |"
        for n, values in by_round.items()
    )
    metadata = (run / "metadata.env").read_text()
    report = f"""# Exp2 multi-round result

更新时间：{datetime.now(timezone.utc).isoformat(timespec='seconds')}；最新运行 `{run_id}`。

- 4 轮、{len(step_rows)} actions；只统计 action wall time：{sum(durations):.3f} ms。
- 全部 action 中位数 {statistics.median(durations):.3f} ms，最大值 {max(durations):.3f} ms。
- 非零 action：{', '.join(failures) or '无'}。
- 跨轮持久化 oracle：{'通过' if oracle_ok else '失败'}。
- 初始启动、checkpoint、TrEnv-X 镜像重建和 restore 均在测量窗口之外，不进入上述数字。

| round | actions | action total (ms) | median (ms) | max (ms) |
| ---: | ---: | ---: | ---: | ---: |
{round_lines}

## Restore 后、每轮 action 前的 guest 内存

| round | guest used (MiB) | page cache (MiB) |
| ---: | ---: | ---: |
{chr(10).join(memory_lines)}

单位均为 MiB。`guest used = MemTotal - MemFree`，表示 guest 当前未空闲的内存；`page
cache = Cached + Buffers - Shmem`，表示文件页缓存与 block buffer，排除 tmpfs/shared memory。
该表使用各轮 runner 的首个 baseline 样本；round 2–4 可直接观察上一轮 checkpoint 后的
restore 状态。
{host_pmem_section}

## Transition diagnostics（不纳入统计）

| after round | checkpoint (ns) | restore (ns) | image rebuild (ns) |
| ---: | ---: | ---: | ---: |
{transition_lines}

## Metadata

```text
{metadata.rstrip()}
```
"""
    (output / "summary.md").write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
