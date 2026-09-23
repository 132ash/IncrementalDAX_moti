# Prettier #14400：AgentENV 结果

运行 `bash motivation/experiments/run.sh agentenv prettier-14400` 后，此目录会出现：

- `summary.md`：延迟、内存分项、正确性和测量限制；
- `figures/latency-by-action.svg`：每个 action/tool 的运行时延；
- `figures/memory-breakdown.svg`：guest 和 host 的基础/峰值内存；
- `raw/<run-id>/`：逐 action 日志、逐点内存、patch、环境与清理记录。
