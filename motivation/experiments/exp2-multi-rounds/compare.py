#!/usr/bin/env python3
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path


SYSTEMS = (
    ("AgentENV / preserve page cache", "agentenv-preserve-cache"),
    ("AgentENV / drop page cache", "agentenv-drop-cache"),
    ("TrEnv-X / drop page cache + rebuild FS", "trenvx"),
)


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def read_metadata(path: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)


def number(row: dict[str, str], key: str) -> int:
    return int(row[key])


def memory_metrics(row: dict[str, str]) -> dict[str, int]:
    total = number(row, "MemTotal_kib")
    page_cache = max(
        number(row, "Cached_kib")
        + number(row, "Buffers_kib")
        - number(row, "Shmem_kib"),
        0,
    )
    return {
        "used": max(total - number(row, "MemFree_kib"), 0),
        "page_cache": page_cache,
    }


def load_system(results: Path, label: str, directory: str) -> dict[str, object]:
    root = results / directory
    run_id = (root / "latest-run.txt").read_text().strip()
    run = root / "raw" / run_id
    metadata = read_metadata(run / "metadata.env")
    by_round: dict[int, float] = {}
    failures: list[str] = []
    memory: dict[int, dict[str, int]] = {}
    host_pmem: dict[int, int] = {}
    action_count = 0
    for round_no in range(1, 5):
        actions = read_tsv(run / "rounds" / str(round_no) / "steps.tsv")
        action_count += len(actions)
        by_round[round_no] = sum(int(row["duration_ns"]) for row in actions) / 1_000_000
        failures.extend(
            f"r{round_no}/{row['step']}={row['exit_code']}" for row in actions if row["exit_code"] != "0"
        )
        samples = read_tsv(run / "rounds" / str(round_no) / "guest-memory.tsv")
        baseline = next(row for row in samples if row["phase"] == "baseline")
        memory[round_no] = memory_metrics(baseline)
    host_pmem_path = run / "host-pmem.tsv"
    if host_pmem_path.exists():
        host_pmem = {int(row["round"]): int(row["mapping_bytes"]) for row in read_tsv(host_pmem_path)}
    oracle_ok = (run / "oracle-exit-code.txt").read_text().strip() == "0"
    return {
        "label": label,
        "directory": directory,
        "run_id": run_id,
        "metadata": metadata,
        "by_round": by_round,
        "total": sum(by_round.values()),
        "action_count": action_count,
        "failures": failures,
        "oracle_ok": oracle_ok,
        "memory": memory,
        "host_pmem": host_pmem,
    }


def main() -> int:
    repo = Path(__file__).resolve().parents[3]
    results = repo / "motivation/results/exp2-multi-rounds"
    data = [load_system(results, *system) for system in SYSTEMS]
    manifest_shas = {item["metadata"]["rounds_sha256"] for item in data}  # type: ignore[index]
    if manifest_shas != {"99b5ad92442e77fc93c525914e797298c2ffb97297b30b50fba01973e7a836dc"}:
        raise RuntimeError(f"unexpected or mismatched action manifests: {manifest_shas}")
    if any(item["action_count"] != 32 or item["failures"] or not item["oracle_ok"] for item in data):
        raise RuntimeError("comparison requires 32 successful actions and a passing oracle for every baseline")

    preserve_total = float(data[0]["total"])
    summary_rows = []
    for item in data:
        total = float(item["total"])
        delta = (total / preserve_total - 1) * 100
        summary_rows.append(
            f"| {item['label']} | `{item['run_id']}` | {total:.3f} | {delta:+.1f}% | 32/32 | 通过 |"
        )
    round_rows = []
    for round_no in range(1, 5):
        values = [float(item["by_round"][round_no]) for item in data]  # type: ignore[index]
        round_rows.append(
            f"| {round_no} | {values[0]:.3f} | {values[1]:.3f} | {values[2]:.3f} |"
        )
    used_rows = []
    cache_rows = []
    for round_no in range(1, 5):
        used = [float(item["memory"][round_no]["used"]) / 1024 for item in data]  # type: ignore[index]
        used_rows.append(
            f"| {round_no} | {used[0]:.1f} | {used[1]:.1f} | {used[2]:.1f} |"
        )
        values = [float(item["memory"][round_no]["page_cache"]) / 1024 for item in data]  # type: ignore[index]
        cache_rows.append(
            f"| {round_no} | {values[0]:.1f} | {values[1]:.1f} | {values[2]:.1f} |"
        )
    trenvx_pmem = data[2]["host_pmem"]  # type: ignore[index]
    host_pmem_section = ""
    if trenvx_pmem:
        host_pmem_rows = "\n".join(
            f"| {round_no} | {trenvx_pmem[round_no] / 1024 / 1024:.1f} |" for round_no in range(1, 5)
        )
        host_pmem_section = f"""

## TrEnv-X host virtio-pmem rootfs mapping

| round | host pmem mapping capacity (MiB) |
| ---: | ---: |
{host_pmem_rows}

TrEnv-X 将只读 rootfs 作为 `/dev/pmem0` 映射。该容量是 host 文件映射容量，独立于 guest
RAM，**不包含**在上面的 guest used 或 page cache 中；它也不等同于运行时 host RSS。
"""

    report = f"""# Exp2 multi-round baseline comparison

更新时间：{datetime.now(timezone.utc).isoformat(timespec='seconds')}。

三组使用同一 workload image、同一份 action manifest（SHA-256
`{next(iter(manifest_shas))}`）和相同的 2 vCPU / 4096 MiB 配置。每组均完成 4 轮、
32/32 actions，且跨轮文件修改 oracle 通过。

## Action wall time

| baseline | run ID | 32 actions total (ms) | vs. preserve | actions | oracle |
| --- | --- | ---: | ---: | ---: | --- |
{chr(10).join(summary_rows)}

这里严格只汇总 guest runner 内每条 action 的单调时钟耗时。初始 sandbox 启动、四次
checkpoint、四次 restore，以及 TrEnv-X 每轮从最新 writable rootfs 重建模板的耗时均不计入。

| round | AgentENV preserve (ms) | AgentENV drop (ms) | TrEnv-X (ms) |
| ---: | ---: | ---: | ---: |
{chr(10).join(round_rows)}

在本次单次运行中，AgentENV 清 cache 相比保留 cache 的 action 总时长增加
{(float(data[1]['total']) / preserve_total - 1) * 100:.1f}%；TrEnv-X 相比 AgentENV 保留 cache
减少 {(1 - float(data[2]['total']) / preserve_total) * 100:.1f}%。这是一次完整 baseline run，
不是多次重复后的统计推断。

## Restore 后、每轮 action 前的 guest used

| round | AgentENV preserve (MiB) | AgentENV drop (MiB) | TrEnv-X (MiB) |
| ---: | ---: | ---: | ---: |
{chr(10).join(used_rows)}

`guest used = MemTotal - MemFree`，表示 guest 当前未空闲的内存。

## Restore 后、每轮 action 前的 page cache

| round | AgentENV preserve (MiB) | AgentENV drop (MiB) | TrEnv-X (MiB) |
| ---: | ---: | ---: | ---: |
{chr(10).join(cache_rows)}

`page cache = Cached + Buffers - Shmem`，表示文件页缓存与 block buffer，排除 tmpfs/shared
memory。round 1 是初始模板状态；round 2–4 是上一轮 checkpoint/restore 后、执行本轮第一个
action 前的 guest baseline。原始 action、内存样本、stdout/stderr、patch 和 transition 诊断数据
分别保存在各 baseline 的 `raw/<run-id>/` 下。
{host_pmem_section}

"""
    (results / "summary.md").write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
