# Exp1：单任务冒烟与轨迹回放

在 AgentENV 和 TrEnv-X 上执行同一份 Prettier #14400 的 26 步开源 shell 轨迹，检查任务执行、正确性 oracle 与观测链路。任务来源和固定镜像见 [workload 说明](../../../docs/workload/workload-prettier-14400.md)。

## 运行

先完成[部署](../../../docs/deployment/README.md)，再从仓库根目录执行：

```bash
bash motivation/experiments/run.sh agentenv prettier-14400
conda activate hybridfs
bash motivation/experiments/run.sh trenvx prettier-14400 setup
bash motivation/experiments/run.sh trenvx prettier-14400
```

TrEnv-X 首次或有意重建模板时才执行 setup。两侧使用 2 vCPU / 4096 MiB，默认在动作前清除 guest cache。AgentENV 冷启动后上传动作；TrEnv-X 将相同动作装入 DAX 基础模板。准备、启动、传输和独立 oracle 不计入动作时间。

## 测量与验收

- 26 个动作逐步记录耗时、退出码、stdout/stderr、guest 内存和最终 patch；默认动作超时 60 s、guest 内存采样间隔 20 ms。
- 保留原轨迹中的 `rg/applypatch` 缺失失败，不能因此提前停止。
- 第 24 步输出必须正确展开 SVG 内 JavaScript；检查 26 步完整性与 oracle，结合最终 diff 判断结果。
- host 采集 cgroup 和 VMM RSS/PSS。guest page cache、host file cache 与 pmem 映射容量分别解释。

结果位于 `motivation/results/exp1-single-app-smoke/{agentenv,trenvx}/`。TrEnv-X 分析器读取同一实验的 AgentENV 结果生成比较；两侧必须使用相同输入与缓存策略。

## 维护与详细说明

- [AgentENV 适配](systems/agentenv/README.md)：缓存、可选 Direct I/O、清理与采集。
- [TrEnv-X 适配](systems/trenvx/README.md)：构建、DAX 检查与结果。
- [固定动作目录](workloads/prettier-14400/README.md)。

正常运行自动清理实例；被强制中断后可依据已记录 ID 清理：

```bash
bash motivation/experiments/run.sh agentenv prettier-14400 cleanup
```
