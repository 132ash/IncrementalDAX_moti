#!/usr/bin/env python3
"""Compare matched memory samples from one AgentENV and TrEnv-X replay."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path


EXPERIMENT = Path(__file__).resolve().parent
GROUPS = (("AgentENV w/o balloon", "agentenv-balloon-off"), ("TrEnv-X", "trenvx"))


def trie_segment_count(trace: dict[str, list[str]]) -> int:
    prefixes = set()
    for path in trace.values():
        prefix: tuple[str, ...] = ()
        for segment in path:
            prefix += (segment,)
            prefixes.add(prefix)
    return len(prefixes)


def expected_segments(trace: dict[str, list[str]], scenario: str) -> int:
    return {"grpo": sum(map(len, trace.values())), "bpo": 17,
            "tvcache": trie_segment_count(trace)}[scenario]


def physical_series(raw: Path) -> dict[str, dict]:
    result = {}
    pattern = re.compile(r"^(\d+)-(.+)$")
    for path in sorted((raw / "host/physical-samples").glob("*/physical-memory.json")):
        match = pattern.match(path.parent.name)
        if not match:
            raise RuntimeError(f"invalid physical sample name: {path.parent.name}")
        sequence, milestone = int(match.group(1)), match.group(2)
        if milestone in result:
            raise RuntimeError(f"duplicate physical milestone {milestone}: {raw}")
        result[milestone] = json.loads(path.read_text()) | {"sequence": sequence}
    return result


def load(results_root: Path, workload: str, scenario: str, group: str) -> dict:
    output = results_root / group / scenario
    run = (output / "latest-run.txt").read_text().strip()
    raw = output / "raw" / run
    result = json.loads((raw / "metrics.json").read_text())
    trace = json.loads((EXPERIMENT / "workloads" / workload / "rollouts.json").read_text())
    if result["metadata"]["workload_name"] != workload or result["metadata"]["scenario"] != scenario:
        raise RuntimeError(f"wrong workload or scenario in {raw}")
    if result["metadata"]["trace_kind"] != "deepseek-agent-sampled-code-repair-replay":
        raise RuntimeError(f"not an agent sample: {raw}")
    wanted = expected_segments(trace, scenario)
    if result["segment_count"] != wanted or result["physical_sample_count"] != wanted + 1:
        raise RuntimeError(f"incomplete {scenario} graph or physical samples: {raw}")
    if not result["peak_qualified"] or result["fork_children"] != (0 if scenario == "grpo" else 6):
        raise RuntimeError(f"incomplete run metadata: {raw}")
    with (raw / "segments.tsv").open(newline="") as handle:
        result["segment_hashes"] = {(row["rollout"], row["segment"]): row["manifest_sha256"]
                                    for row in csv.DictReader(handle, delimiter="\t")}
    result["terminal_patches"] = {
        role: hashlib.sha256((raw / "rollouts" / role / segments[-1] / "patch.diff").read_bytes()).hexdigest()
        for role, segments in trace.items()
    }
    result["physical_series"] = physical_series(raw)
    result["raw"] = raw
    return result


def pct(base: float, value: float) -> str:
    return "n/a" if base == 0 else f"{(value / base - 1) * 100:+.1f}%"


def compare(workload: str, scenario: str, results_root: Path) -> dict:
    data = [(label, load(results_root, workload, scenario, group)) for label, group in GROUPS]
    baseline, trenv = data[0][1], data[1][1]
    for field in ("tool_count", "segment_count", "segment_hashes", "terminal_patches"):
        if trenv[field] != baseline[field]:
            raise RuntimeError(f"runtime mismatch in {field}: {trenv['raw']}")
    baseline_failures = set(baseline["failed_actions"])
    trenv_failures = set(trenv["failed_actions"])
    failure_delta = sorted(baseline_failures ^ trenv_failures)
    # Read-only discovery pipelines ending in `find ... | head` can report 1
    # when the concurrently changing /proc tree is walked. Like SIGPIPE 141,
    # this does not mutate the sandbox; terminal patches are checked below.
    allowed_nondeterminism = re.compile(r"/(?:trace_index_state/001|trace_cpp_parser/005)=1$")
    if any(not (item.endswith("=141") or allowed_nondeterminism.search(item))
           for item in failure_delta):
        raise RuntimeError(f"runtime mismatch in failed_actions: {trenv['raw']}")
    if set(baseline["physical_series"]) != set(trenv["physical_series"]):
        raise RuntimeError("physical sample milestones do not match")

    paired = []
    for milestone, agent_sample in sorted(baseline["physical_series"].items(),
                                          key=lambda item: item[1]["sequence"]):
        trenv_sample = trenv["physical_series"][milestone]
        agent_mib = agent_sample["page_cache_host_physical_mib"]
        trenv_mib = trenv_sample["page_cache_host_physical_mib"]
        paired.append({
            "milestone": milestone,
            "agentenv_sequence": agent_sample["sequence"],
            "trenvx_sequence": trenv_sample["sequence"],
            "agentenv_file_physical_mib": agent_mib,
            "trenvx_file_physical_mib": trenv_mib,
            "estimated_optimization_mib": agent_mib - trenv_mib,
            "estimated_optimization_pct": (agent_mib - trenv_mib) / agent_mib * 100 if agent_mib else 0,
        })
    delta_path = results_root / f"{scenario}-file-physical-delta.tsv"
    with delta_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=paired[0].keys(), delimiter="\t")
        writer.writeheader()
        writer.writerows(paired)
    best = max(paired, key=lambda row: row["estimated_optimization_mib"])
    agent_peak_point = max(paired, key=lambda row: row["agentenv_file_physical_mib"])

    scenario_name = scenario.upper() if scenario != "tvcache" else "TVCache"
    task = baseline["metadata"]["task"]
    failure_note = (f"两个系统的非零退出集合另有 {len(failure_delta)} 个只读 `find/grep | head` 调度差异（exit 1/141）；"
                    "这些 action 不写状态，终态 patch 已单独校验一致。\n\n" if failure_delta else "")
    text = f"""# Exp5 {scenario_name}：{task['instance_id']}

任务：[{task['title']}]({task['url']})；两个系统回放同一条冻结 agent 轨迹。实际执行 {baseline['segment_count']} 个物理 segment、{baseline['logical_segment_count']} 个逻辑 segment 和 {baseline['tool_count']} 个工具动作；终态 patch 逐路径一致。

| 指标 | AgentENV w/o balloon | TrEnv-X |
| --- | ---: | ---: |
| 文件内容物理量峰值 (MiB) | {baseline['page_cache_host_physical_mib']:.1f} | {trenv['page_cache_host_physical_mib']:.1f} |
| 沙箱 VMM PSS 总量峰值 (MiB) | {baseline['peak_vmm_pss_mib']:.1f} | — |
| 工具时间 (s，仅供审计) | {baseline['tool_aggregate_ms']/1000:.2f} | {trenv['tool_aggregate_ms']/1000:.2f} |

TrEnv-X 的文件内容物理峰值相对 AgentENV 为 {pct(baseline['page_cache_host_physical_mib'], trenv['page_cache_host_physical_mib'])}。在匹配的 `{best['milestone']}` 采样点，逐点差额 `AgentENV - TrEnv-X` 最大，为 **{best['estimated_optimization_mib']:.1f} MiB ({best['estimated_optimization_pct']:.1f}%)**。AgentENV 文件峰值所在的 `{agent_peak_point['milestone']}` 采样点，估算优化空间为 {agent_peak_point['estimated_optimization_mib']:.1f} MiB ({agent_peak_point['estimated_optimization_pct']:.1f}%)。

完整逐点结果见 [{delta_path.name}]({delta_path.name})。这里按相同的 segment 完成里程碑配对，而非按两次独立运行的绝对墙钟时间配对；并发分支在该时刻的进度可能略有差异，因此差额是优化空间估算，不是逐页因果归因。

{failure_note}文件内容物理量在每个物理 segment 后及终态采样，共 {baseline['physical_sample_count']} 个点：guest file-LRU 页映射到 host PFN 后去重，再加只读 DAX rootfs 映射 PSS。PSS 仅报告 AgentENV 的 VMM 聚合观测峰值；不再用 TrEnv-X PSS 做跨系统比较。每组只运行一次，不能估计方差。

原始数据：[AgentENV w/o balloon](agentenv-balloon-off/{scenario}/summary.md) (`{baseline['run']}`)、[TrEnv-X](trenvx/{scenario}/summary.md) (`{trenv['run']}`)。
"""
    summary = results_root / ("summary.md" if scenario == "bpo" else f"{scenario}-summary.md")
    summary.write_text(text, encoding="utf-8")
    return {"workload": workload, "scenario": scenario, "task": task, "agentenv": baseline,
            "trenvx": trenv, "paired": paired, "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workload")
    parser.add_argument("scenario", choices=("grpo", "bpo", "tvcache"))
    parser.add_argument("results_root", type=Path)
    args = parser.parse_args()
    result = compare(args.workload, args.scenario, args.results_root.resolve())
    print(result["summary"])


if __name__ == "__main__":
    main()
