# Exp5 TVCache：prettier__prettier-6604

任务：[TypeScript double-parenthesis semantic repair](https://github.com/prettier/prettier/issues/6603)；两个系统回放同一条冻结 agent 轨迹。实际执行 13 个物理 segment、35 个逻辑 segment 和 68 个工具动作；终态 patch 逐路径一致。

| 指标 | AgentENV w/o balloon | TrEnv-X |
| --- | ---: | ---: |
| 文件内容物理量峰值 (MiB) | 800.9 | 384.7 |
| 沙箱 VMM PSS 总量峰值 (MiB) | 3208.7 | — |
| 工具时间 (s，仅供审计) | 37.98 | 40.80 |

TrEnv-X 的文件内容物理峰值相对 AgentENV 为 -52.0%。在匹配的 `after-backbone-backbone_finish` 采样点，逐点差额 `AgentENV - TrEnv-X` 最大，为 **585.3 MiB (74.1%)**。AgentENV 文件峰值所在的 `terminal-retained` 采样点，估算优化空间为 416.3 MiB (52.0%)。

完整逐点结果见 [tvcache-file-physical-delta.tsv](tvcache-file-physical-delta.tsv)。这里按相同的 segment 完成里程碑配对，而非按两次独立运行的绝对墙钟时间配对；并发分支在该时刻的进度可能略有差异，因此差额是优化空间估算，不是逐页因果归因。

文件内容物理量在每个物理 segment 后及终态采样，共 14 个点：guest file-LRU 页映射到 host PFN 后去重，再加只读 DAX rootfs 映射 PSS。PSS 仅报告 AgentENV 的 VMM 聚合观测峰值；不再用 TrEnv-X PSS 做跨系统比较。每组只运行一次，不能估计方差。

原始数据：[AgentENV w/o balloon](agentenv-balloon-off/tvcache/summary.md) (`20260920T154554Z-tvcache-agentenv`)、[TrEnv-X](trenvx/tvcache/summary.md) (`20260921T082835Z-tvcache-trenvx-incremental-dax`)。
