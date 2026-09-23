# Exp5：三类真实代码修复任务的文件内容物理量对比

本轮比较 **AgentENV w/o balloon** 与 **TrEnv-X** 在同一条冻结 DeepSeek agent 轨迹上的 BPO、GRPO 和 TVCache。由于两套系统的内存共享机制与 VMM 运行时不同，不再比较 TrEnv-X PSS；只报告两侧文件内容物理量峰值、AgentENV 沙箱 VMM PSS 总量峰值，以及相同 segment 完成里程碑上的文件内容物理量差额 `AgentENV - TrEnv-X`。

截至 2026-09-21，三个任务的 BPO、GRPO 和 TVCache 均已完成。当前 TrEnv-X 会把 checkpoint 时的 writable upper 封存为继承式只读 DAX layer；父分支和子分支都从带该历史层的干净模板继续，并各自使用新的私有 upper。

| 调度 | 任务 | AgentENV 文件峰值 (MiB) | TrEnv-X 文件峰值 (MiB) | TrEnv-X 相对变化 | AgentENV PSS 峰值 (MiB) | 文件峰值减少量占 AgentENV PSS | 最大逐点估算空间 (MiB) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BPO | Prettier 6604 | 579.5 | 411.6 | -29.0% | 3114.7 | 5.4% | 226.9 |
|  | Xarray 6992 | 1126.6 | 442.6 | -60.7% | 3879.7 | 17.6% | 685.4 |
|  | Sphinx 7590 | 348.8 | 198.1 | -43.2% | 2451.6 | 6.1% | 180.7 |
| GRPO | Prettier 6604 | 1597.7 | 432.1 | -73.0% | 7652.2 | 15.2% | 1244.1 |
|  | Xarray 6992 | 2554.4 | 731.5 | -71.4% | 8528.4 | 21.4% | 1840.9 |
|  | Sphinx 7590 | 1035.3 | 452.7 | -56.3% | 6471.9 | 9.0% | 585.2 |
| TVCache | Prettier 6604 | 800.9 | 384.7 | -52.0% | 3208.7 | 13.0% | 585.3 |
|  | Xarray 6992 | 1144.9 | 440.8 | -61.5% | 3814.8 | 18.5% | 704.3 |
|  | Sphinx 7590 | 364.6 | 198.3 | -45.6% | 2678.2 | 6.2% | 202.6 |

## 观察

GRPO 的 7 条轨迹完全独立执行，没有运行期公共 checkpoint，因此只使用 base-DAX；三个任务的文件峰值相对 AgentENV 分别下降 73.0%、71.4% 和 56.3%。BPO 与 TVCache 会把公共运行前缀封成增量 DAX 层。相对旧的 base-DAX-only TrEnv-X，BPO 的 Prettier、Xarray、Sphinx 峰值又分别减少 11.9、119.7、67.5 MiB；TVCache 的 Prettier、Xarray 分别再减少 38.8、113.9 MiB。Sphinx TVCache 此前没有 TrEnv-X 完成值，本轮测得 198.3 MiB。

GRPO 新旧值有 4.4–13.3 MiB 波动，但它不创建 checkpoint layer，不能把该差异解释成增量 DAX 效果。新增机制的直接证据来自 BPO/TVCache：历史 upper 被封成 `checkpoint-*.ext4`，各后代 hard-link 同一 inode 并通过 virtio-pmem + ext4 DAX 读取；新写入仍只进入各自私有 upper。

TVCache 的物理执行数取决于冻结轨迹中是否还有更长公共前缀。Prettier 的 early/late 分支各共享一个 inspect segment，因此只执行 13 个物理 segment；Xarray 和 Sphinx 的分支在 checkpoint 后立即分歧，需要 17 个，和 BPO 相同。这里的 TVCache 收益因此不仅由调度名称决定，也由具体轨迹的前缀结构决定。

## 口径与限制

文件内容物理量在每个物理 segment 完成后及终态采样：guest file-LRU 页映射到 host PFN 后去重，再加只读 base/checkpoint DAX 映射 PSS。BPO 每组 18 个点，GRPO 36 个点；TVCache 的 Prettier 为 14 个点，Xarray/Sphinx 为 18 个点。文件峰值是这些离散采样点的最大值，可能漏掉 segment 内瞬时尖峰。

“文件峰值减少量占 AgentENV PSS”按 `(AgentENV 文件峰值 − TrEnv-X 文件峰值) / AgentENV PSS 峰值` 计算。它把文件内容物理量差额投影到 AgentENV VMM PSS 的量级上，仅用于说明比例；两类指标的峰值不要求同时发生，不能将该比例解释为实测的总 PSS 降幅。

逐点差额按相同的 `after-<role>-<segment>` 或 `terminal-retained` 里程碑配对，不按两次独立运行的绝对墙钟时间配对。GRPO 中其他并发分支在配对时刻的进度可能略有差异，因此该差额只作为优化空间估算，不能解释为逐页因果收益。AgentENV PSS 是 0.1 秒 VMM 聚合观测峰值，不含 daemon、kernel 和 VMM 外 host 块缓存；文件物理量与 PSS 有重叠，不能相加。每组只正式运行一次，不能估计方差。

两个系统的 segment manifest 与七条终态 patch 均逐路径一致。Xarray/Sphinx 的部分只读 `find/grep | head` action 因管道调度或 `/proc` 遍历出现 exit 1/141 差异；这些 action 不写状态，任务页已披露。失败或主动中止的尝试没有更新 `latest-run.txt`，不进入本表。

## 详细结果

- Prettier 6604：[BPO](prettier-6604/summary.md)、[GRPO](prettier-6604/grpo-summary.md)、[TVCache](prettier-6604/tvcache-summary.md)
- Xarray 6992：[BPO](xarray-6992/summary.md)、[GRPO](xarray-6992/grpo-summary.md)、[TVCache](xarray-6992/tvcache-summary.md)
- Sphinx 7590：[BPO](sphinx-7590/summary.md)、[GRPO](sphinx-7590/grpo-summary.md)、[TVCache](sphinx-7590/tvcache-summary.md)

每个已完成的系统对都有对应的 `{bpo,grpo,tvcache}-file-physical-delta.tsv`，记录两个系统的采样序号、文件内容物理量、逐点 MiB 差额和百分比。实验实现与冻结轨迹见 [实验目录](../../experiments/exp5-RL-fork/README.md)。
