# Xarray #6992：Dataset 索引状态一致性

用于 [Exp3](../../motivation/experiments/exp3-RL-fork/README.md)。任务实例为 `pydata__xarray-6992`，本地任务元数据标记为 SWE-bench Verified、难度 `>4 hours`，基线 commit 为 `45c0a114e2b7b27b83c9618bc05b36afac82183c`。

索引重构后，Dataset 的 `_coord_names` 可能包含 `_variables` 中已不存在的名称。`reset_index(..., drop=True)` 等路径遗留不一致状态，使 DataVariables 长度/迭代、repr 或 groupby 出错，最小复现可触发 `ValueError: __len__() should return >= 0`。

## 固定输入

```text
ghcr.io/epoch-research/swe-bench.eval.x86_64.pydata__xarray-6992@sha256:c05101ef7105599eca1b7d15279a2928ac5453876cd2b83008deb9165d752655
```

[输入目录](../../motivation/experiments/exp3-RL-fork/workloads/xarray-6992-rl-fork/README.md)中的 `task.json` 固定问题、镜像和分阶段目标；`agent-sampling.json` 保存 DeepSeek 的自适应工具调用。测量重放冻结命令，不重新问模型。

| 路径 | 调查或验证重点 |
| --- | --- |
| 主干 | `read_repo → trace_index_state → core_patch → core_verify → backbone_finish`；追踪 variables/coords/indexes 不变量，修复并测试 |
| early 1–3 | 分别探索 drop=True/缺失变量、DataVariables 长度与 repr、groupby 丢弃 NaN 后的索引清理 |
| late 1–3 | 分别补充 DataArray 一致性、drop/convert/rename 参数组合、groupby 与残留坐标名 |

读取 Xarray 实现和测试，运行最小 Python 复现及聚焦 Dataset/DataArray/reset_index/groupby pytest。无依赖安装、全量测试或合成文件扫描。

## 规模与验收

七条路径共 35 个逻辑 segment；GRPO 执行 35 个物理 segment，BPO 和 TVCache 各 17 个。现有 BPO 成对运行执行 104 个工具动作。各分支有自己的 inspect 段，没有 Prettier 那样额外可复用的 inspect 前缀。

保留失败探索与测试输出；比较器核验两系统的 manifest、动作数和七条终态 patch，另审计只读发现命令的退出差异。该一致性检查不等于 SWE-bench 隐藏测试通过。

[当前 BPO 结果](../../motivation/results/exp3-RL-fork/xarray-6992/summary.md)及其他调度按 `motivation/results/exp3-RL-fork/xarray-6992/<system>/<scenario>/` 归档。
