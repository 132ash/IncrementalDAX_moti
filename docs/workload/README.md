# Workload 索引

四个真实代码修复任务对应五种实验输入：Prettier #6604 分别用于人工整理的四轮回放和模型采样的多分支回放。镜像均固定到 digest，任务代码位于 `/testbed`，依赖随镜像预装；正式计时不安装依赖、不运行完整测试套件。

| 任务 | 所属实验 | 轨迹来源与规模 | 主要访问与修改 |
| --- | --- | --- | --- |
| [Prettier #14400](workload-prettier-14400.md) | Exp1 | Tracebench mini-SWE-agent/GPT-5，原样保留 26 个 shell 动作 | HTML/SVG parser、JavaScript 嵌入格式化 |
| [Prettier #6604](workload-prettier-6604.md) | Exp2 | 参考 Tracebench OpenHands 轨迹，整理为 4 × 8 个动作 | TypeScript indexed-access 括号打印、Node/Jest |
| [Prettier #6604](workload-prettier-6604.md) | Exp3 | DeepSeek 采样 7 条路径；35 个逻辑 segment | 双重括号、union/conditional/keyof 语义 |
| [Xarray #6992](workload-xarray-6992.md) | Exp3 | DeepSeek 采样 7 条路径；35 个逻辑 segment | Dataset/DataArray 索引不变量、reset_index/groupby |
| [Sphinx #7590](workload-sphinx-7590.md) | Exp3 | DeepSeek 采样 7 条路径；35 个逻辑 segment | C++ 字面量 parser、AST、rendering/ID |

## 输入与真实性

Exp1 是开源轨迹的动作级回放；Exp2 是保留任务访问路径的人工整理；Exp3 是模型根据工具反馈采样一次后冻结的修复轨迹。真实任务不等于生产 sandbox fork trace：Exp3 的 checkpoint 位置和分支目标由实验者指定，没有训练 RL policy，也没有采集线上 fork 频率。

Exp3 每条主干有 5 个 segment；前两段完成调查，前四段完成候选修改与验证。早期三分支继承前两段，后期三分支继承前四段，各再执行两个 segment，因此逻辑段数为 `5 + 3×4 + 3×6 = 35`。实际执行段数取决于调度，见 [Exp3 README](../../motivation/experiments/exp3-RL-fork/README.md)。

每个 Exp3 workload 保存：

- `task.json`：任务、基线 commit、固定镜像；Xarray/Sphinx 还包含分阶段目标。
- `agent-sampling.json`：模型消息、实际 shell 命令、输出、退出码和采样元数据。
- `rollouts.json`：七条路径与共享前缀。
- `segments/*/actions.tsv`：逐动作编号、SHA256 与实际回放命令。
- `plan.py`：只验证上述冻结 manifest，不重新采样。旧的未被图引用的 segment 不计入当前实验。

采样脚本在 `--network none` Docker 容器中执行工具，host 调用 `deepseek-chat` 的 `chat/completions` 接口；key 只由 host 从本地文件读取，不写入轨迹。Prettier 使用其目录内 `sample_rollouts.py`，另两个任务使用实验根目录 `sample_task.py`。这些脚本用于产生新输入，**不是复现已有结果的必需步骤**。

失败探索保留在回放中，不能看到非零退出就删除该动作。正确性要结合聚焦测试、任务 oracle 与最终 patch；两系统 patch 相同只说明回放一致，不能代替独立隐藏测试。
