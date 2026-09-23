# Exp5 BPO：prettier__prettier-6604

任务：[TypeScript double-parenthesis semantic repair](https://github.com/prettier/prettier/issues/6603)；两个系统回放同一条冻结 agent 轨迹。实际执行 17 个物理 segment、35 个逻辑 segment 和 84 个工具动作；终态 patch 逐路径一致。

| 指标 | AgentENV w/o balloon | TrEnv-X |
| --- | ---: | ---: |
| 文件内容物理量峰值 (MiB) | 579.5 | 411.6 |
| 沙箱 VMM PSS 总量峰值 (MiB) | 3114.7 | — |
| 工具时间 (s，仅供审计) | 43.99 | 44.35 |

TrEnv-X 的文件内容物理峰值相对 AgentENV 为 -29.0%。在匹配的 `after-late_3-late_inspect` 采样点，逐点差额 `AgentENV - TrEnv-X` 最大，为 **226.9 MiB (40.1%)**。AgentENV 文件峰值所在的 `terminal-retained` 采样点，估算优化空间为 167.9 MiB (29.0%)。

完整逐点结果见 [bpo-file-physical-delta.tsv](bpo-file-physical-delta.tsv)。这里按相同的 segment 完成里程碑配对，而非按两次独立运行的绝对墙钟时间配对；并发分支在该时刻的进度可能略有差异，因此差额是优化空间估算，不是逐页因果归因。

文件内容物理量在每个物理 segment 后及终态采样，共 18 个点：guest file-LRU 页映射到 host PFN 后去重，再加只读 DAX rootfs 映射 PSS。PSS 仅报告 AgentENV 的 VMM 聚合观测峰值；不再用 TrEnv-X PSS 做跨系统比较。每组只运行一次，不能估计方差。

原始数据：[AgentENV w/o balloon](agentenv-balloon-off/bpo/summary.md) (`20260919T034324Z-bpo-agentenv`)、[TrEnv-X](trenvx/bpo/summary.md) (`20260921T080328Z-bpo-trenvx-incremental-dax`)。
