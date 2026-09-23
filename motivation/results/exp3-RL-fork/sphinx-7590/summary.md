# Exp5 BPO：sphinx-doc__sphinx-7590

任务：[C++ User Defined Literals not supported](https://github.com/sphinx-doc/sphinx/issues/7590)；两个系统回放同一条冻结 agent 轨迹。实际执行 17 个物理 segment、35 个逻辑 segment 和 104 个工具动作；终态 patch 逐路径一致。

| 指标 | AgentENV w/o balloon | TrEnv-X |
| --- | ---: | ---: |
| 文件内容物理量峰值 (MiB) | 348.8 | 198.1 |
| 沙箱 VMM PSS 总量峰值 (MiB) | 2451.6 | — |
| 工具时间 (s，仅供审计) | 30.28 | 27.14 |

TrEnv-X 的文件内容物理峰值相对 AgentENV 为 -43.2%。在匹配的 `after-early_1-early_1_finish` 采样点，逐点差额 `AgentENV - TrEnv-X` 最大，为 **180.7 MiB (52.8%)**。AgentENV 文件峰值所在的 `terminal-retained` 采样点，估算优化空间为 179.6 MiB (51.5%)。

完整逐点结果见 [bpo-file-physical-delta.tsv](bpo-file-physical-delta.tsv)。这里按相同的 segment 完成里程碑配对，而非按两次独立运行的绝对墙钟时间配对；并发分支在该时刻的进度可能略有差异，因此差额是优化空间估算，不是逐页因果归因。

两个系统的非零退出集合另有 1 个只读 `find/grep | head` 调度差异（exit 1/141）；这些 action 不写状态，终态 patch 已单独校验一致。

文件内容物理量在每个物理 segment 后及终态采样，共 18 个点：guest file-LRU 页映射到 host PFN 后去重，再加只读 DAX rootfs 映射 PSS。PSS 仅报告 AgentENV 的 VMM 聚合观测峰值；不再用 TrEnv-X PSS 做跨系统比较。每组只运行一次，不能估计方差。

原始数据：[AgentENV w/o balloon](agentenv-balloon-off/bpo/summary.md) (`20260920T151108Z-bpo-agentenv`)、[TrEnv-X](trenvx/bpo/summary.md) (`20260921T085629Z-bpo-trenvx-incremental-dax`)。
