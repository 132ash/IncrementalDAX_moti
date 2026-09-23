# Prettier #14400：固定回放输入

本目录由 Exp1 的两个系统共用。`actions/` 包含按顺序回放的 26 个 shell 工具调用，`actions.tsv` 固定顺序与哈希；任务、来源和镜像 digest 见[workload 文档](../../../../../docs/workload/workload-prettier-14400.md)。

`guest-runner.sh` 供 TrEnv-X 镜像使用，记录逐动作延迟、guest memory、vmstat、patch 及 stdout/stderr。AgentENV 使用一个私有 guest runner 调整上传和产物路径，仍回放同一份 `actions/` 与 manifest。

输入依赖固定 PolyBench 镜像的 `/testbed` 布局。原轨迹中 `rg` 与 `applypatch` 两个命令不可用的动作保留为探索记录，不视为 runner 故障。正确性检查使用第 24 步 SVG script 输出；运行命令见 [Exp1 README](../../README.md)。
