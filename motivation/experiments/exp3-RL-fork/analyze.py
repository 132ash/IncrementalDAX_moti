#!/usr/bin/env python3
"""Summarize tool-only latency and host physical memory for one exp5 run."""
from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def mib(kib: float) -> float:
    return kib / 1024


def guest_cache(row: dict[str, str]) -> int:
    return max(0, int(row["Cached_kib"]) + int(row["Buffers_kib"]) - int(row["Shmem_kib"]))


def trie_segment_count(trace: dict[str, list[str]]) -> int:
    prefixes = set()
    for path in trace.values():
        prefix: tuple[str, ...] = ()
        for segment in path:
            prefix += (segment,)
            prefixes.add(prefix)
    return len(prefixes)


def summarize(raw: Path) -> dict:
    metadata = json.loads((raw / "metadata.json").read_text())
    segments = rows(raw / "segments.tsv")
    workload = metadata["workload_name"]
    trace = json.loads((Path(__file__).parent / "workloads" / workload / "rollouts.json").read_text())
    tools: list[dict] = []
    cache_deltas: list[dict] = []
    for item in segments:
        directory = raw / "rollouts" / item["rollout"] / item["segment"]
        steps = rows(directory / "steps.tsv")
        memory = rows(directory / "guest-memory.tsv")
        before = guest_cache(next(row for row in memory if row["phase"] == "baseline"))
        after = guest_cache(next(row for row in reversed(memory) if row["phase"] == "complete"))
        cache_deltas.append({**item, "before_kib": before, "after_kib": after, "delta_kib": after - before})
        for step in steps:
            tools.append({**item, **step, "duration_ns": int(step["duration_ns"])})
    failures = [f"{row['rollout']}/{row['segment']}/{row['step']}={row['exit_code']}" for row in tools if row["exit_code"] != "0"]
    host = rows(raw / "host/memory-samples.tsv")
    terminal = [row for row in host if row["phase"] == "terminal-retained" and int(row["vmm_count"]) == 7]
    if not terminal:
        raise RuntimeError(f"no seven-VMM terminal samples: {raw}")
    host_metrics = {key: statistics.median(int(row[key]) for row in terminal) for key in (
        "vmm_pss_kib", "vmm_pss_anon_kib", "vmm_pss_file_kib", "vmm_rss_kib", "cgroup_current_bytes",
        "cgroup_anon_bytes", "cgroup_file_bytes", "cgroup_kernel_bytes",
    )}
    active_samples = [row for row in host if row["phase"] not in ("cleanup", "done")]
    peak = max(active_samples, key=lambda row: int(row["vmm_pss_kib"]))
    seven_peak = max((row for row in active_samples if int(row["vmm_count"]) == 7),
                     key=lambda row: int(row["vmm_pss_kib"]))
    setup = [row for row in host if row["phase"] == "setup" and int(row["vmm_count"]) == 0]
    cgroup_baseline = statistics.median(int(row["cgroup_current_bytes"]) for row in setup) if setup else 0
    cgroup_peak = max(active_samples, key=lambda row: int(row["cgroup_current_bytes"]))
    mapping = rows(raw / "host/mapping-snapshots.tsv")
    dax_pss_kib = sum(int(row["pss_kib"]) for row in mapping
                      if row["phase"] == "terminal-retained" and (
                          Path(row["pathname"]).name == "rootfs.ext4" or
                          Path(row["pathname"]).name.startswith("checkpoint-")))
    memory_image_pss_kib = sum(int(row["pss_kib"]) for row in mapping
                               if row["phase"] == "terminal-retained" and Path(row["pathname"]).name == "memory-ranges")
    ublk_pss_kib = sum(int(row["pss_kib"]) for row in mapping
                       if row["phase"] == "terminal-retained" and Path(row["pathname"]).name.startswith("ublkb"))
    guest_cache_terminal_kib = sum(item["after_kib"] for item in cache_deltas if item["segment"] == trace[item["rollout"]][-1])
    final_guest_rows = []
    for role, path in trace.items():
        samples = rows(raw / "rollouts" / role / path[-1] / "guest-memory.tsv")
        final_guest_rows.append(next(row for row in reversed(samples) if row["phase"] == "complete"))
    guest_anon_kib = sum(int(row["AnonPages_kib"]) for row in final_guest_rows)
    guest_used_kib = sum(int(row["MemTotal_kib"]) - int(row["MemFree_kib"]) for row in final_guest_rows)
    physical = json.loads((raw / "host/physical-memory.json").read_text())
    physical_samples = [json.loads(path.read_text()) | {"sample_path": str(path.relative_to(raw))}
                        for path in sorted((raw / "host/physical-samples").glob("*/physical-memory.json"))]
    legacy_terminal_only = not physical_samples
    if legacy_terminal_only:
        physical_samples = [physical | {"sample_path": "host/physical-memory.json (terminal only)"}]
    cache_peak = max(physical_samples, key=lambda item: item["page_cache_host_physical_mib"])
    category_kib = {key: 0 for key in ("dax", "memory_image", "ublk", "unnamed", "vmm_other")}
    for row in mapping:
        if row["phase"] != "terminal-retained":
            continue
        basename = Path(row["pathname"]).name
        key = ("dax" if basename == "rootfs.ext4" or basename.startswith("checkpoint-") else
               "memory_image" if basename == "memory-ranges" else
               "ublk" if basename.startswith("ublkb") else
               "unnamed" if not row["pathname"] else "vmm_other")
        category_kib[key] += int(row["pss_kib"])
    executed = {(item["rollout"], item["segment"]) for item in segments}
    expected = {(role, segment) for role, path in trace.items() for segment in path}
    # A shared prefix is executed once, then inherited. Check the exact expected physical executions.
    expected_count = {
        "grpo": len(expected),
        "bpo": 17,
        "tvcache": trie_segment_count(trace),
    }[metadata["scenario"]]
    if len(segments) != expected_count:
        raise RuntimeError(f"incomplete {metadata['scenario']} graph: got {len(segments)}, expected {expected_count}")
    events = rows(raw / "events.tsv")
    result = {
        "metadata": metadata, "run": raw.name, "tool_count": len(tools), "segment_count": len(segments),
        "expected_segment_count": expected_count, "logical_segment_count": len(expected),
        "failed_actions": failures,
        "tool_aggregate_ms": sum(row["duration_ns"] for row in tools) / 1e6,
        "tool_by_rollout_ms": {role: sum(row["duration_ns"] for row in tools if row["rollout"] == role) / 1e6 for role in trace},
        "terminal_vmm_pss_mib": mib(host_metrics["vmm_pss_kib"]),
        "peak_vmm_pss_mib": mib(int(peak["vmm_pss_kib"])),
        "peak_seven_vmm_pss_mib": mib(int(seven_peak["vmm_pss_kib"])),
        "peak_seven_vmm_phase": seven_peak["phase"],
        "peak_vmm_pss_anon_mib": mib(int(peak["vmm_pss_anon_kib"])),
        "peak_vmm_pss_file_mib": mib(int(peak["vmm_pss_file_kib"])),
        "peak_vmm_private_dirty_mib": mib(int(peak["vmm_private_dirty_kib"])),
        "peak_vmm_count": int(peak["vmm_count"]),
        "peak_vmm_phase": peak["phase"],
        "peak_cgroup_charge_delta_mib": max(0, int(cgroup_peak["cgroup_current_bytes"]) - cgroup_baseline) / 1024**2,
        "peak_cgroup_charge_mib": int(cgroup_peak["cgroup_current_bytes"]) / 1024**2,
        "cgroup_baseline_charge_mib": cgroup_baseline / 1024**2,
        "terminal_vmm_pss_anon_mib": mib(host_metrics["vmm_pss_anon_kib"]),
        "terminal_vmm_pss_file_mib": mib(host_metrics["vmm_pss_file_kib"]),
        "terminal_cgroup_current_mib": host_metrics["cgroup_current_bytes"] / 1024**2,
        "terminal_cgroup_anon_mib": host_metrics["cgroup_anon_bytes"] / 1024**2,
        "terminal_cgroup_file_mib": host_metrics["cgroup_file_bytes"] / 1024**2,
        "terminal_cgroup_kernel_mib": host_metrics["cgroup_kernel_bytes"] / 1024**2,
        "terminal_guest_cache_logical_mib": mib(guest_cache_terminal_kib),
        "terminal_guest_anon_logical_mib": mib(guest_anon_kib),
        "terminal_guest_used_logical_mib": mib(guest_used_kib),
        "terminal_guest_other_used_logical_mib": mib(guest_used_kib - guest_cache_terminal_kib - guest_anon_kib),
        "terminal_dax_layers_pss_mib": mib(dax_pss_kib),
        "terminal_memory_image_pss_mib": mib(memory_image_pss_kib),
        "terminal_ublk_mapping_pss_mib": mib(ublk_pss_kib),
        "terminal_mapping_pss_mib": {key: mib(value) for key, value in category_kib.items()},
        "terminal_mapping_pss_total_mib": mib(sum(category_kib.values())),
        "page_cache_host_physical_mib": cache_peak["page_cache_host_physical_mib"],
        "sandbox_vmm_host_physical_pss_mib": mib(int(peak["vmm_pss_kib"])),
        "peak_cache_sample": cache_peak["sample_path"],
        "physical_sample_count": len(physical_samples),
        "peak_qualified": not legacy_terminal_only,
        "physical_cache_peak_probe": cache_peak,
        "physical_cache_probe": physical,
        "measured_guest_cache_growth_mib": mib(sum(item["delta_kib"] for item in cache_deltas)),
        "fork_events": sum(row["event"] == "fork" for row in events),
        "fork_children": sum(len(row["children"].split(",")) for row in events if row["event"] == "fork"),
    }
    (raw / "metrics.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def report(raw: Path, result: dict) -> None:
    output = raw.parents[1] / "summary.md"
    balloon_mode = result["metadata"].get("agentenv_balloon_mode")
    system_title = result["metadata"]["system"] + (f" / balloon {balloon_mode}" if balloon_mode else "")
    memory_title = "全程峰值口径" if result["peak_qualified"] else "旧终态物理样本与 VMM 监测峰值（不可配对比较）"
    cache_title = "文件内容采样峰值" if result["peak_qualified"] else "文件内容终态样本"
    sample_explanation = (f"文件内容在每个 segment 完成后及终态逐页采样，共 {result['physical_sample_count']} 次；最大样本来自 `{result['peak_cache_sample']}`。两次采样之间的瞬时峰值可能更高。"
                          if result["peak_qualified"] else
                          "此旧运行只在终态逐页采样，文件内容数值不是峰值；仅用于分层功能审计，不纳入峰值比较。")
    implementation = ("TrEnv-X 在 checkpoint 时封存父 VM 的 writable upper，构建继承历史层的只读 DAX lower 链，"
                      "并从干净模板恢复父分支和子分支；同一历史层在所有后代中保持同一 host inode，后代各用新的私有 upper。"
                      "rootfs 之外的 `/tmp` 临时状态单独捕获和恢复，不计作 DAX layer。"
                      if result["metadata"]["system"] == "trenvx" else
                      "AgentENV 在分叉点创建持久快照模板；子沙箱各有私有可写层，同模板复用只读内存快照设备。")
    task = result["metadata"]["task"]
    text = f"""# Exp5 {result['metadata']['scenario'].upper()} / {system_title}

运行：`{result['run']}`；固定 trace SHA-256：`{result['metadata']['trace_sha256']}`。

- 已执行 {result['segment_count']} 个 segment、{result['tool_count']} 个工具 action；非零 exit：{', '.join(result['failed_actions']) or '无'}；派生 {result['fork_children']} 个 child。
- 工具执行时间 **{result['tool_aggregate_ms']/1000:.2f} s**；仅包括工具 action，不包括 checkpoint、模板构建、启动或测量。

| {memory_title} | MiB |
| --- | ---: |
| **{cache_title}**：guest file-LRU host PFN 去重 + DAX 文件映射 PSS | **{result['page_cache_host_physical_mib']:.1f}** |
| **VMM 映射监测峰值**：聚合 PSS | **{result['sandbox_vmm_host_physical_pss_mib']:.1f}** |

{sample_explanation} VMM PSS 监控目标间隔为 0.1 秒，取全程观测峰（阶段 `{result['peak_vmm_phase']}`，当时 {result['peak_vmm_count']} 个 VMM）；七条 rollout 同时存活期间的峰值另为 {result['peak_seven_vmm_pss_mib']:.1f} MiB。两个主指标峰值不要求同时发生。VMM PSS 不含 daemon、kernel 或未映射的 host 块文件缓存，不能称为全机沙箱关联内存。原始逐页探针和映射保存在 `raw/{result['run']}/host/`。

在 VMM PSS 峰值样本里，匿名页 PSS 为 {result['peak_vmm_pss_anon_mib']:.1f} MiB，文件映射 PSS 为 {result['peak_vmm_pss_file_mib']:.1f} MiB；内存共享和已释放 guest 页的宿主驻留均影响前者。

{implementation} 工具动作来自 DeepSeek 对固定任务 [{task['instance_id']}]({task['url']}) 的一次交互式采样；正式测量回放同一冻结轨迹。它不是 RL 策略训练或在线模型推理时延测量。
"""
    output.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    path = Path(sys.argv[1]).resolve()
    report(path, summarize(path))
