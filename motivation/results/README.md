# 实验结果

结果按实验归档，`raw/<run-id>/` 保存单次运行，`summary.md`、SVG 和 TSV 为派生报告。不要手工合并不同 run；分析器重新运行会更新派生文件。

**当前 checkout 不包含 raw 数据**，`.gitignore` 忽略 `**/raw/`。仓库中的报告、图表及派生表可直接阅读；要复算已有报告，需从实验机补齐对应 raw（以报告和 `latest-run.txt` 中的 run ID 为准），或按部署文档重新运行。仅有 summary 不能完成原始样本审计。

## Exp1 与 Exp2

| 结果 | 内容 |
| --- | --- |
| [Exp1 AgentENV](exp1-single-app-smoke/agentenv/summary.md) | 26 步回放，guest/host 内存与正确性 |
| [Exp1 TrEnv-X 与比较](exp1-single-app-smoke/trenvx/summary.md) | 基础镜像 DAX；[补充分析](exp1-single-app-smoke/trenvx/analysis.md) |
| [Exp2 三组比较](exp2-multi-rounds/summary.md) | AgentENV preserve/drop-cache 与 TrEnv-X，四轮动作时间 |

Exp1/2 的 TrEnv-X 仅对基础镜像使用 DAX，checkpoint 历史写入仍走 block upper。

## Exp3：按任务与调度读取

| 任务 | GRPO | BPO | TVCache |
| --- | --- | --- | --- |
| Prettier #6604 | [报告](exp3-RL-fork/prettier-6604/grpo-summary.md) | [报告](exp3-RL-fork/prettier-6604/summary.md) | [报告](exp3-RL-fork/prettier-6604/tvcache-summary.md) |
| Xarray #6992 | [报告](exp3-RL-fork/xarray-6992/grpo-summary.md) | [报告](exp3-RL-fork/xarray-6992/summary.md) | [报告](exp3-RL-fork/xarray-6992/tvcache-summary.md) |
| Sphinx #7590 | [报告](exp3-RL-fork/sphinx-7590/grpo-summary.md) | [报告](exp3-RL-fork/sphinx-7590/summary.md) | [报告](exp3-RL-fork/sphinx-7590/tvcache-summary.md) |

主比较为 `<task>/agentenv-balloon-off/<scenario>` 与 `<task>/trenvx/<scenario>`。每组 `latest-run.txt` 指向该组接受的 raw run。TrEnv-X 在此实验中将 checkpoint upper 封存为 DAX 层；主表比较文件内容物理量，VMM PSS 仅列 AgentENV，工具时间仅供审计。

Exp3 根目录的 `agentenv/`、`agentenv-balloon-on/`、`agentenv-balloon-off/`、`trenvx/`、`summary.md` 和 [memory-diagnosis.md](exp3-RL-fork/memory-diagnosis.md) 保留早期 Prettier/balloon 与内存归因记录。它们的轨迹版本和采样口径可能不同，优先阅读上表按任务组织的成对报告。

当前目录名 Exp3 对应历史 Exp5，已归档报告的标题和 raw 元数据可能仍显示 Exp5。未收录旧 `exp3-fork` 与 `exp4-realistic-fork`。这些历史名称不应被当作新的实验组。

## 解释限制

当前 Exp3 每任务、每调度、每系统只有一次成对运行，不能估计方差。样本按 segment 里程碑配对而非同时刻配对，文件内容峰值也可能漏掉段内波动。两系统终态 patch 相同证明回放一致性，不能替代独立隐藏测试。完整指标定义和复算命令见[执行与验收](../../docs/deployment/experiments.md)。
