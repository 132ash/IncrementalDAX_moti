# Exp2 multi-round result

更新时间：2026-09-15T06:11:07+00:00；最新运行 `host-pmem-trenvx-20260915`。

- 4 轮、32 actions；只统计 action wall time：7920.881 ms。
- 全部 action 中位数 61.025 ms，最大值 1397.381 ms。
- 非零 action：无。
- 跨轮持久化 oracle：通过。
- 初始启动、checkpoint、TrEnv-X 镜像重建和 restore 均在测量窗口之外，不进入上述数字。

| round | actions | action total (ms) | median (ms) | max (ms) |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 8 | 1559.713 | 40.199 | 887.326 |
| 2 | 8 | 1400.472 | 60.218 | 558.926 |
| 3 | 8 | 2460.386 | 68.193 | 1397.381 |
| 4 | 8 | 2500.310 | 86.347 | 1125.224 |

## Restore 后、每轮 action 前的 guest 内存

| round | guest used (MiB) | page cache (MiB) |
| ---: | ---: | ---: |
| 1 | 178.4 | 9.6 |
| 2 | 157.2 | 4.0 |
| 3 | 144.7 | 4.0 |
| 4 | 136.9 | 4.0 |

单位均为 MiB。`guest used = MemTotal - MemFree`，表示 guest 当前未空闲的内存；`page
cache = Cached + Buffers - Shmem`，表示文件页缓存与 block buffer，排除 tmpfs/shared memory。
该表使用各轮 runner 的首个 baseline 样本；round 2–4 可直接观察上一轮 checkpoint 后的
restore 状态。


## Host virtio-pmem rootfs mapping（TrEnv-X）

| round | host pmem mapping capacity (MiB) |
| ---: | ---: |
| 1 | 3806.0 |
| 2 | 3806.0 |
| 3 | 3806.0 |
| 4 | 3806.0 |

这是 host 上作为 `/dev/pmem0` 暴露给 guest 的只读 rootfs 文件映射容量。它独立于 guest
RAM，不包含在上表的 `guest used` 或 `page cache` 中；容量也不是运行时 host RSS。


## Transition diagnostics（不纳入统计）

| after round | checkpoint (ns) | restore (ns) | image rebuild (ns) |
| ---: | ---: | ---: | ---: |
| 1 | 1624184111 | 1088231420 | 2954587416 |
| 2 | 1751046880 | 1081477741 | 3061362572 |
| 3 | 1580859637 | 1091493154 | 2928647585 |
| 4 | 1819604304 | 1074248788 | 3074624871 |

## Metadata

```text
run_id=host-pmem-trenvx-20260915
system=trenvx
cache_mode=drop
workload_image=ghcr.io/timesler/swe-polybench.eval.x86_64.prettier__prettier-6604@sha256:8159d38fcbd6d5f09402d93d3e15cf2a891058ddd835a224f1d6b3357a87cc94
template_id=prettier-6604-exp2-ch-dax
sandbox_cpu=2
sandbox_memory_mib=4096
started_utc=2026-09-15T06:08:34+00:00
rounds_sha256=99b5ad92442e77fc93c525914e797298c2ffb97297b30b50fba01973e7a836dc
latency_scope=actions_only
transition_latency_included=false
filesystem_restore=rebuild-template-from-latest-writable-rootfs
host_pmem_metric=virtio-pmem-read-only-rootfs-mapping-capacity
host_pmem_rootfs_bytes=3990880256
```
