# IncrementalDAX 前期实验

本项目为 [研究动机](docs/moti/moti.md) 提供实验依据：在真实代码修复任务的读取、修改及多分支执行过程中，测量 block 文件系统与直接映射只读文件层的内存开销，探索将 checkpoint 历史写入转为共享 DAX 层的收益。

项目包含 AgentENV、TrEnv-X 两个修改后的 baseline，以及三个固定轨迹实验。任务来自真实项目；测量阶段重放冻结的 shell 命令，不调用模型。

| 实验 | 工作负载 | 回答的问题 |
| --- | --- | --- |
| [Exp1：单任务回放](motivation/experiments/exp1-single-app-smoke/README.md) | Prettier #14400，26 个动作 | 两套系统能否执行相同任务，观测和正确性检查是否可用？ |
| [Exp2：四轮保存与恢复](motivation/experiments/exp2-multi-rounds/README.md) | Prettier #6604，4 × 8 个动作 | checkpoint 保留或清除 guest cache 后，后续执行有何变化？ |
| [Exp3：多分支轨迹](motivation/experiments/exp3-RL-fork/README.md) | Prettier #6604、Xarray #6992、Sphinx #7590 | 同一组七条轨迹采用 GRPO/BPO/TVCache 调度时，历史文件层共享能节省多少物理内存？ |

## 阅读与复现

- [Baseline 修改](docs/baselines/README.md)：源代码修改、实验适配及对比边界。
- [部署与测试](docs/deployment/README.md)：Linux 主机准备、服务构建、实验命令和验收。
- [Workload 索引](docs/workload/README.md)：任务来源、固定版本、轨迹构造和验证方式。
- [实验入口](motivation/experiments/README.md)与[结果索引](motivation/results/README.md)：脚本、原始数据和比较报告。

当前 checkout 包含结果报告，未包含被 Git 忽略的 `raw/` 原始运行数据；复算已有报告需从实验机补齐，或重新运行实验。

```text
baselines/                 # 两个 Git 子模块及其本地修改
docs/                      # 动机、baseline、部署与 workload 说明
motivation/experiments/     # 实验协议、固定输入、系统适配和分析器
motivation/results/        # 按实验、任务、系统归档的测量结果
```

部署需要 Linux x86_64、KVM、Docker 和相应内核能力；Windows 工作目录可用于编辑与离线检查，不能直接运行这些 microVM 实验。首次运行请先阅读部署文档；已部署主机可从 Exp1 开始：

```bash
# 在仓库根目录执行
bash motivation/experiments/run.sh agentenv prettier-14400
conda activate hybridfs
bash motivation/experiments/run.sh trenvx prettier-14400 setup
bash motivation/experiments/run.sh trenvx prettier-14400
```

## 解释结果时的边界

Exp1/2 的 TrEnv-X 只将基础镜像直接映射；Exp3 额外封存 checkpoint 写入为 DAX 层，属于增量 DAX 实验扩展。两者不能混称为未经修改的 TrEnv-X。

主要时间指标只计 guest 工具执行，不含模型等待、启动和 checkpoint 构建。Exp3 主比较使用文件内容物理内存，当前各任务/调度的成对结果各运行一次，不能据此估计方差或生产环境平均收益。GRPO/BPO/TVCache 是调度形状，实验未训练 RL policy。

当前目录中的 `exp3-RL-fork` 沿用历史实验 Exp5；部分脚本默认值、模板名和已有报告仍写 `exp5`。研究动机还引用了本仓库未收录的历史实验。可用目录和命令以[实验入口说明](motivation/experiments/README.md)为准。
