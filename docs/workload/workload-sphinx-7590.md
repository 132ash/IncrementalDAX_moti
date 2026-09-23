# Sphinx #7590：C++ 用户定义字面量

用于 [Exp3](../../motivation/experiments/exp3-RL-fork/README.md)。任务实例为 `sphinx-doc__sphinx-7590`，本地任务元数据标记为 SWE-bench Verified、难度 `>4 hours`，基线 commit 为 `2e506c5ab457cba743bb47eb5b8c8eb9dd51d23d`。

Sphinx C++ domain parser 无法解析带自定义后缀的字面量，例如 `6.62607015e-34q_J * 1q_s`，报 `Expected end of definition`。任务需补充数值、字符串及字符字面量后缀解析，同时保持 AST 表示、渲染和 ID 生成一致。

## 固定输入

```text
ghcr.io/epoch-research/swe-bench.eval.x86_64.sphinx-doc__sphinx-7590@sha256:577ebfcce825e4c9621e066dc1c8375443be94bbc6de30b9368e422b8f123731
```

[输入目录](../../motivation/experiments/exp3-RL-fork/workloads/sphinx-7590-rl-fork/README.md)保存任务、DeepSeek 工具调用记录、七条路径和命令 manifest。测量重放冻结动作，模型决策不随 baseline 变化。

| 路径 | 调查或验证重点 |
| --- | --- |
| 主干 | `read_repo → trace_cpp_parser → core_patch → core_verify → backbone_finish`；复现、追踪词法/AST、实现并测试 |
| early 1–3 | 分别探索数值 token 与后缀词法、AST/describe/ID、表达式优先级及后缀绑定 |
| late 1–3 | 分别补充十进制/指数/十六进制/整数、渲染和 ID 稳定性、字符串/字符与内建后缀兼容 |

动作以源码和 expression tests 读取、最小复现、代码修改、聚焦 C++ domain pytest 为主，不运行全量 Sphinx 测试或安装依赖。

## 规模与验收

七条路径共 35 个逻辑 segment；GRPO/BPO/TVCache 分别执行 35/17/17 个物理 segment。现有 BPO 成对运行执行 104 个工具动作。六条分支的 inspect 段各不相同，所以 TVCache 段数与 BPO 相同。

保留失败探索和测试输出，比较器检查输入、七条终态 patch 及允许的只读命令退出差异。聚焦测试用于观察修复行为；未执行独立隐藏评测时，不把“完成轨迹”写成“任务已解决”。

[当前 BPO 结果](../../motivation/results/exp3-RL-fork/sphinx-7590/summary.md)及其他调度按 `motivation/results/exp3-RL-fork/sphinx-7590/<system>/<scenario>/` 归档。
