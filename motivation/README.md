# Motivation experiments

这里存放 `docs/moti.md` 对应的可复现实验，而不是 workload 输入本身。

```text
motivation/
├── experiments/                         # 可复用脚本和实验说明
│   ├── lib/                             # 多个实验可共用的 host 工具
│   ├── run.sh                           # 统一入口：system + workload + action
│   ├── exp1-single-app-smoke/           # 单应用 smoke 实验及其固定 workload
│       ├── workloads/prettier-14400/
│       └── systems/{agentenv,trenvx}/
│   ├── exp2-multi-rounds/               # 四轮 checkpoint/restore
│       ├── workloads/prettier-6604/
│       └── systems/{agentenv,trenvx}/
│   ├── exp3-fork/                       # 父两轮后 fork 四条 divergent 分支
│       ├── workloads/prettier-6604-fork/
│       └── systems/{agentenv,trenvx}/
│   └── exp4-realistic-fork/             # 5 peer 读取父未预热文件并采集 host PSS
│       ├── workloads/prettier-6604-realistic-fork/
│       └── systems/{agentenv,trenvx}/
└── results/
    ├── exp1-single-app-smoke/
    │   └── <system>/                    # 每个系统的 summary、figures、raw/<run-id>
    ├── exp2-multi-rounds/
    │   └── <system>/                    # 每个系统的 summary、figures、raw/<run-id>
    ├── exp3-fork/
    │   └── <system>/                    # 每个系统的 summary、figures、raw/<run-id>
    └── exp4-realistic-fork/
        └── <system>/                    # 每个系统的 summary、figures、raw/<run-id>
```

workload 的固定输入（task、trajectory、26 个 action）随实验协议保存在
`experiments/exp1-single-app-smoke/workloads/prettier-14400/`。单次测量数据不会写回输入
目录。四轮 checkpoint/restore workload 位于
`experiments/exp2-multi-rounds/workloads/prettier-6604/`，结果写入
`results/exp2-multi-rounds/`。fork workload 位于
`experiments/exp3-fork/workloads/prettier-6604-fork/`，结果写入 `results/exp3-fork/`。
真实冷文件 fan-out workload 位于
`experiments/exp4-realistic-fork/workloads/prettier-6604-realistic-fork/`，结果写入
`results/exp4-realistic-fork/`。

运行方法见
[`experiments/exp1-single-app-smoke/README.md`](experiments/exp1-single-app-smoke/README.md) 和
[`experiments/exp2-multi-rounds/README.md`](experiments/exp2-multi-rounds/README.md)、
[`experiments/exp3-fork/README.md`](experiments/exp3-fork/README.md)、
[`experiments/exp4-realistic-fork/README.md`](experiments/exp4-realistic-fork/README.md)。
