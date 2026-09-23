# Exp2 multi-round result

更新时间：2026-09-15T05:00:08+00:00；最新运行 `mem-breakdown-preserve-20260915`。

- 4 轮、32 actions；只统计 action wall time：12130.265 ms。
- 全部 action 中位数 49.032 ms，最大值 4128.358 ms。
- 非零 action：无。
- 跨轮持久化 oracle：通过。
- 初始启动、checkpoint、TrEnv-X 镜像重建和 restore 均在测量窗口之外，不进入上述数字。

| round | actions | action total (ms) | median (ms) | max (ms) |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 8 | 4909.515 | 34.181 | 4128.358 |
| 2 | 8 | 1572.710 | 28.330 | 712.982 |
| 3 | 8 | 2576.764 | 80.809 | 1417.098 |
| 4 | 8 | 3071.277 | 58.906 | 1641.464 |

## Restore 后、每轮 action 前的 guest 内存

| round | guest used (MiB) | page cache (MiB) |
| ---: | ---: | ---: |
| 1 | 68.1 | 28.8 |
| 2 | 329.7 | 223.5 |
| 3 | 343.7 | 234.8 |
| 4 | 337.7 | 239.4 |

单位均为 MiB。`guest used = MemTotal - MemFree`，表示 guest 当前未空闲的内存；`page
cache = Cached + Buffers - Shmem`，表示文件页缓存与 block buffer，排除 tmpfs/shared memory。
该表使用各轮 runner 的首个 baseline 样本；round 2–4 可直接观察上一轮 checkpoint 后的
restore 状态。

## Transition diagnostics（不纳入统计）

| after round | checkpoint (ns) | restore (ns) | image rebuild (ns) |
| ---: | ---: | ---: | ---: |
| 1 | 843074247 | 180835795 | 0 |
| 2 | 322524514 | 524219719 | 0 |
| 3 | 427786354 | 666076560 | 0 |
| 4 | 367965691 | 480319099 | 0 |

## Metadata

```text
run_id=mem-breakdown-preserve-20260915
system=agentenv
cache_mode=preserve
workload_image=ghcr.io/timesler/swe-polybench.eval.x86_64.prettier__prettier-6604@sha256:8159d38fcbd6d5f09402d93d3e15cf2a891058ddd835a224f1d6b3357a87cc94
sandbox_cpu=2
sandbox_memory_mib=4096
started_utc=2026-09-15T04:35:13+00:00
rounds_sha256=99b5ad92442e77fc93c525914e797298c2ffb97297b30b50fba01973e7a836dc
latency_scope=actions_only
transition_latency_included=false
```
