# Motivation 实验

这里存放 [docs/moti/moti.md](../docs/moti/moti.md) 对应的前期实验。固定输入和运行协议保存在 `experiments/`，单次运行产物保存在 `results/`。

| 目录 | 内容 | 结果 |
| --- | --- | --- |
| [exp1-single-app-smoke](experiments/exp1-single-app-smoke/README.md) | Prettier #14400 的 26 步开源轨迹回放 | [Exp1](results/exp1-single-app-smoke/trenvx/summary.md) |
| [exp2-multi-rounds](experiments/exp2-multi-rounds/README.md) | Prettier #6604 四轮有状态回放，每轮 checkpoint/restore | [Exp2](results/exp2-multi-rounds/summary.md) |
| [exp3-RL-fork](experiments/exp3-RL-fork/README.md) | 三个真实修复任务、七条采样轨迹、三种调度 | [按任务索引](results/README.md) |

复现顺序：先完成[部署](../docs/deployment/README.md)，用 Exp1 检查运行链路，再做 Exp2 或 Exp3。实验目录内的 `workloads/` 是冻结输入；不要在运行时重新采样或改写动作。每次测量使用独立 `raw/<run-id>/`，保留输入哈希、输出、退出码和内存采样，分析结果从 raw 重建。

当前 Exp3 曾命名为 Exp5；历史 `exp3-fork`、`exp4-realistic-fork` 不在本仓库中。具体命令与兼容说明见 [experiments/README.md](experiments/README.md)。
