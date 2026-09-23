# Exp2 multi-round baseline comparison

更新时间：2026-09-15T06:11:25+00:00。

三组使用同一 workload image、同一份 action manifest（SHA-256
`99b5ad92442e77fc93c525914e797298c2ffb97297b30b50fba01973e7a836dc`）和相同的 2 vCPU / 4096 MiB 配置。每组均完成 4 轮、
32/32 actions，且跨轮文件修改 oracle 通过。

## Action wall time

| baseline | run ID | 32 actions total (ms) | vs. preserve | actions | oracle |
| --- | --- | ---: | ---: | ---: | --- |
| AgentENV / preserve page cache | `mem-breakdown-preserve-20260915` | 12130.265 | +0.0% | 32/32 | 通过 |
| AgentENV / drop page cache | `mem-breakdown-drop-20260915` | 22108.421 | +82.3% | 32/32 | 通过 |
| TrEnv-X / drop page cache + rebuild FS | `host-pmem-trenvx-20260915` | 7920.881 | -34.7% | 32/32 | 通过 |

这里严格只汇总 guest runner 内每条 action 的单调时钟耗时。初始 sandbox 启动、四次
checkpoint、四次 restore，以及 TrEnv-X 每轮从最新 writable rootfs 重建模板的耗时均不计入。

| round | AgentENV preserve (ms) | AgentENV drop (ms) | TrEnv-X (ms) |
| ---: | ---: | ---: | ---: |
| 1 | 4909.515 | 5570.049 | 1559.713 |
| 2 | 1572.710 | 4574.380 | 1400.472 |
| 3 | 2576.764 | 6553.872 | 2460.386 |
| 4 | 3071.277 | 5410.121 | 2500.310 |

在本次单次运行中，AgentENV 清 cache 相比保留 cache 的 action 总时长增加
82.3%；TrEnv-X 相比 AgentENV 保留 cache
减少 34.7%。这是一次完整 baseline run，
不是多次重复后的统计推断。

## Restore 后、每轮 action 前的 guest used

| round | AgentENV preserve (MiB) | AgentENV drop (MiB) | TrEnv-X (MiB) |
| ---: | ---: | ---: | ---: |
| 1 | 68.1 | 67.8 | 178.4 |
| 2 | 329.7 | 136.5 | 157.2 |
| 3 | 343.7 | 110.5 | 144.7 |
| 4 | 337.7 | 112.4 | 136.9 |

`guest used = MemTotal - MemFree`，表示 guest 当前未空闲的内存。

## Restore 后、每轮 action 前的 page cache

| round | AgentENV preserve (MiB) | AgentENV drop (MiB) | TrEnv-X (MiB) |
| ---: | ---: | ---: | ---: |
| 1 | 28.8 | 28.7 | 9.6 |
| 2 | 223.5 | 58.0 | 4.0 |
| 3 | 234.8 | 42.4 | 4.0 |
| 4 | 239.4 | 45.7 | 4.0 |

`page cache = Cached + Buffers - Shmem`，表示文件页缓存与 block buffer，排除 tmpfs/shared
memory。round 1 是初始模板状态；round 2–4 是上一轮 checkpoint/restore 后、执行本轮第一个
action 前的 guest baseline。原始 action、内存样本、stdout/stderr、patch 和 transition 诊断数据
分别保存在各 baseline 的 `raw/<run-id>/` 下。


## TrEnv-X host virtio-pmem rootfs mapping

| round | host pmem mapping capacity (MiB) |
| ---: | ---: |
| 1 | 3806.0 |
| 2 | 3806.0 |
| 3 | 3806.0 |
| 4 | 3806.0 |

TrEnv-X 将只读 rootfs 作为 `/dev/pmem0` 映射。该容量是 host 文件映射容量，独立于 guest
RAM，**不包含**在上面的 guest used 或 page cache 中；它也不等同于运行时 host RSS。


