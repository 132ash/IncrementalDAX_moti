# Exp1: single-app smoke

本实验在 AgentENV 和 TrEnv-X 上重放同一份 Prettier #14400 的 26-action 轨迹，检查单应用
端到端执行、结果 oracle 与基础观测链路。workload 是此实验协议的一部分，而不是跨实验的
全局目录；每个系统只保存其启动、镜像、sandbox 和采集适配。

从仓库根目录通过统一入口运行：

```bash
# AgentENV cold-start replay
bash motivation/experiments/run.sh agentenv prettier-14400

# TrEnv-X：首次或重建 template 后先执行 setup
bash motivation/experiments/run.sh trenvx prettier-14400 setup
bash motivation/experiments/run.sh trenvx prettier-14400
```

支持的维护动作可由 `bash motivation/experiments/run.sh --help` 查看。例如 AgentENV 的
遗留 sandbox 清理使用：

```bash
bash motivation/experiments/run.sh agentenv prettier-14400 cleanup
```

结果位于 `motivation/results/exp1-single-app-smoke/{agentenv,trenvx}/`。TrEnv-X 的分析器会
读取同一实验下的 AgentENV 结果来生成对比，因此两侧都必须使用此目录中的固定 workload。
