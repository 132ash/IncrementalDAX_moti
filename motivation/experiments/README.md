# 实验脚本

实验名是一级目录：一个目录包含该实验的 workload、系统私有适配和说明。公共入口是
[`run.sh`](run.sh)，它以 `<system> <workload> [action]` 选择实验内的私有脚本；不要直接
依赖 `systems/` 下的路径。

```text
experiments/
├── run.sh                              # 统一入口和受支持组合的路由表
├── lib/                                # 跨实验复用的 host 采集器
├── exp1-single-app-smoke/              # 一个应用的 smoke/replay 实验
    ├── workloads/prettier-14400/       # 此实验固定的 26-action 输入
    └── systems/
        ├── agentenv/                   # AgentENV 私有生命周期适配
        └── trenvx/                     # TrEnv-X 私有构建、启动和 SDK client
├── exp2-multi-rounds/                  # 四轮 checkpoint/restore 实验
    ├── workloads/prettier-6604/        # 每轮不同的 8-action 输入
    └── systems/{agentenv,trenvx}/      # 两套 checkpoint/restore 适配
├── exp3-fork/                          # 两轮后 fork 四条分支
    ├── workloads/prettier-6604-fork/   # 2 轮 common + 4×2 轮 divergent actions
    └── systems/{agentenv,trenvx}/      # 原生 fork / 共享 COW template 适配
└── exp4-realistic-fork/                # 未预热文件的五实例 fork fan-out
    ├── workloads/prettier-6604-realistic-fork/
    └── systems/{agentenv,trenvx}/      # 原父继续 / 父子均从 snapshot 恢复
```

当前实验的默认运行命令：

```bash
bash motivation/experiments/run.sh agentenv prettier-14400
bash motivation/experiments/run.sh trenvx prettier-14400
```

TrEnv-X 首次运行前需要构建模板：

```bash
bash motivation/experiments/run.sh trenvx prettier-14400 setup
```

四轮实验及两种 AgentENV page-cache policy：

```bash
bash motivation/experiments/run.sh agentenv-page-cache prettier-6604
bash motivation/experiments/run.sh agentenv-drop-cache prettier-6604
bash motivation/experiments/run.sh trenvx prettier-6604 setup
bash motivation/experiments/run.sh trenvx prettier-6604
```

四分支 fork 实验：

```bash
bash motivation/experiments/run.sh agentenv-page-cache prettier-6604-fork
bash motivation/experiments/run.sh agentenv-drop-cache prettier-6604-fork
bash motivation/experiments/run.sh trenvx prettier-6604-fork setup
bash motivation/experiments/run.sh trenvx prettier-6604-fork
python motivation/experiments/exp3-fork/compare.py
```

父未预热文件的真实 fork fan-out 实验：

```bash
bash motivation/experiments/run.sh agentenv prettier-6604-realistic-fork
bash motivation/experiments/run.sh trenvx prettier-6604-realistic-fork setup
bash motivation/experiments/run.sh trenvx prettier-6604-realistic-fork
python motivation/experiments/exp4-realistic-fork/compare.py
```

运行结果按实验名归档到 `motivation/results/<experiment>/<system>/`；每次运行只会新增一个
UTC 时间戳的 `raw/<run-id>/`。
