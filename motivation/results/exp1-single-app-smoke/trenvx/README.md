# Prettier #14400：TrEnv-X 结果

- [`summary.md`](summary.md)：自动生成的 TrEnv-X / AgentENV 比较。
- [`analysis.md`](analysis.md)：guest 内存分项、启动与动作延迟差异，以及可比性限制。
- `raw/20260914T124731Z-trenvx-ch-dax-replay/`：报告对应的已接受运行；raw 未随当前 checkout 收录，复算需补齐。
- `diagnostics/`：保留未完成的部署尝试，包括端口冲突、host iptables 锁 ACL、可选代理路由、guest 文件所有权和最初的第 24 步 oracle 修正；分析器不将其计入结果。

两系统已接受的运行使用相同 action manifest digest，均为单次执行链路验证，不构成具有充分统计依据的性能评测。
