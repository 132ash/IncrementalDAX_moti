# 实验脚本

每个实验包含 `workloads/`（固定任务输入）和 `systems/{agentenv,trenvx}/`（系统适配）；`lib/` 提供 host cgroup、VMM PSS 和内存映射采集器。部署要求见 [docs/deployment](../../docs/deployment/README.md)。所有命令从仓库根目录执行。

## 可用实验

| 实验 | 规模与生命周期 | 运行入口 |
| --- | --- | --- |
| [Exp1](exp1-single-app-smoke/README.md) | 26 个动作；单实例 | 公共 `run.sh` |
| [Exp2](exp2-multi-rounds/README.md) | 4 轮 × 8 个动作；每轮保存并恢复 | 公共 `run.sh` |
| [Exp3](exp3-RL-fork/README.md) | 3 个任务；每任务 7 条轨迹；GRPO/BPO/TVCache | 实验内 `systems/*/run.sh` |

```bash
# Exp1
bash motivation/experiments/run.sh agentenv prettier-14400
conda activate hybridfs
bash motivation/experiments/run.sh trenvx prettier-14400 setup
bash motivation/experiments/run.sh trenvx prettier-14400

# Exp2
bash motivation/experiments/run.sh agentenv-page-cache prettier-6604
bash motivation/experiments/run.sh agentenv-drop-cache prettier-6604
bash motivation/experiments/run.sh trenvx prettier-6604 setup
bash motivation/experiments/run.sh trenvx prettier-6604
python3 motivation/experiments/exp2-multi-rounds/compare.py
```

Exp3 必须同时选择任务镜像、模板和结果目录，完整命令见[多分支测试流程](../../docs/deployment/experiments.md)。首次运行 TrEnv-X 执行 `setup`；已有同名模板时脚本拒绝覆盖。只有有意重建时才使用 `REBUILD_TEMPLATE=1`。

## 当前目录与历史命名

本仓库只有 `exp1-single-app-smoke`、`exp2-multi-rounds`、`exp3-RL-fork`。公共 [run.sh](run.sh) 尚保留旧路由：

- `prettier-6604-fork`、`prettier-6604-realistic-fork` 指向未收录目录，当前不可用。
- `prettier-6604-rl-fork` 指向旧 `exp5-RL-fork`，不能用于当前 Exp3；Xarray/Sphinx 也未注册。
- Exp3 两个 runner 的默认输出仍为 `motivation/results/exp5-RL-fork/...`。按文档显式设置 `OUTPUT_ROOT`，将结果写入当前 `exp3-RL-fork`。
- `/var/lib/trenvx-exp5-cow`、`trenvx-exp5` cgroup、guest 的 `mixfs-exp5` 路径及模板名是现有脚本的内部约定，可以保留。生成报告的标题仍可能显示 Exp5。

本说明采用现有脚本的真实入口，不依赖旧路由。

## 输入、输出与测量

- Exp1/2 的动作位于 `actions/*.sh`；manifest 固定顺序和哈希。Exp3 用 `rollouts.json` 表示轨迹图，用 `segments/*/actions.tsv` 保存实际命令，`plan.py` 只验证冻结输入。
- 输出使用独立 `raw/<run-id>/`；`RUN_ID` 可显式指定，已有目录会被拒绝覆盖。Exp3 按 `<task>/<system>/<scenario>` 归档。
- 工具时间只覆盖动作本身；生命周期时间单独记录。guest `Cached`、host cgroup `file`、VMM PSS 和 DAX 映射容量含义不同，不得混加。
- 分析器会重写所属结果目录的 `summary.md`、图表或派生表；raw 保持逐次归档。当前 checkout 未包含被 Git 忽略的 raw，重建已有报告前需从实验机补齐。验收标准见[部署与测试](../../docs/deployment/experiments.md)。
