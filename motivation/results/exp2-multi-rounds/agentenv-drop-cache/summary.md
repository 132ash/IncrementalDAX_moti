# Exp2 multi-round result

更新时间：2026-09-15T05:00:09+00:00；最新运行 `mem-breakdown-drop-20260915`。

- 4 轮、32 actions；只统计 action wall time：22108.421 ms。
- 全部 action 中位数 87.543 ms，最大值 4522.051 ms。
- 非零 action：无。
- 跨轮持久化 oracle：通过。
- 初始启动、checkpoint、TrEnv-X 镜像重建和 restore 均在测量窗口之外，不进入上述数字。

| round | actions | action total (ms) | median (ms) | max (ms) |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 8 | 5570.049 | 51.019 | 4522.051 |
| 2 | 8 | 4574.380 | 62.112 | 2260.145 |
| 3 | 8 | 6553.872 | 109.372 | 2533.447 |
| 4 | 8 | 5410.121 | 118.618 | 2912.060 |

## Restore 后、每轮 action 前的 guest 内存

| round | guest used (MiB) | page cache (MiB) |
| ---: | ---: | ---: |
| 1 | 67.8 | 28.7 |
| 2 | 136.5 | 58.0 |
| 3 | 110.5 | 42.4 |
| 4 | 112.4 | 45.7 |

单位均为 MiB。`guest used = MemTotal - MemFree`，表示 guest 当前未空闲的内存；`page
cache = Cached + Buffers - Shmem`，表示文件页缓存与 block buffer，排除 tmpfs/shared memory。
该表使用各轮 runner 的首个 baseline 样本；round 2–4 可直接观察上一轮 checkpoint 后的
restore 状态。

## Transition diagnostics（不纳入统计）

| after round | checkpoint (ns) | restore (ns) | image rebuild (ns) |
| ---: | ---: | ---: | ---: |
| 1 | 855630568 | 216883198 | 0 |
| 2 | 460921223 | 287717973 | 0 |
| 3 | 587207801 | 256948913 | 0 |
| 4 | 486550784 | 306317434 | 0 |

## Metadata

```text
run_id=mem-breakdown-drop-20260915
system=agentenv
cache_mode=drop
workload_image=ghcr.io/timesler/swe-polybench.eval.x86_64.prettier__prettier-6604@sha256:8159d38fcbd6d5f09402d93d3e15cf2a891058ddd835a224f1d6b3357a87cc94
sandbox_cpu=2
sandbox_memory_mib=4096
started_utc=2026-09-15T04:34:32+00:00
rounds_sha256=99b5ad92442e77fc93c525914e797298c2ffb97297b30b50fba01973e7a836dc
latency_scope=actions_only
transition_latency_included=false
```
