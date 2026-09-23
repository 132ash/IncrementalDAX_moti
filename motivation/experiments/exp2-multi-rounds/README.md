# Exp2：四轮 checkpoint 与恢复

以真实 Prettier #6604 修复任务为原型，整理为四轮有状态回放，每轮 8 个不同的读取、搜索、修改和 Node/Jest 验证动作。每轮末尾保存 checkpoint，再从它恢复；第四轮也执行保存与恢复，使生命周期一致。输入不是原 OpenHands 轨迹的逐字重放，详见[workload 说明](../../../docs/workload/workload-prettier-6604.md)。

## 运行矩阵

```bash
# AgentENV：checkpoint 保留 guest page cache
bash motivation/experiments/run.sh agentenv-page-cache prettier-6604
# AgentENV：checkpoint 前清 guest cache
bash motivation/experiments/run.sh agentenv-drop-cache prettier-6604
# TrEnv-X：先构建基础模板
conda activate hybridfs
bash motivation/experiments/run.sh trenvx prettier-6604 setup
bash motivation/experiments/run.sh trenvx prettier-6604
python3 motivation/experiments/exp2-multi-rounds/compare.py
```

从仓库根目录运行，前置条件见[部署文档](../../../docs/deployment/README.md)。资源为 2 vCPU / 4096 MiB；默认动作超时 300 s，guest 内存采样间隔 20 ms。

## 两套保存与恢复方式

AgentENV 使用持久 snapshot 保存文件系统、进程状态与内存映像。`preserve` 模式不干预 page cache；`drop` 模式在每次 checkpoint 前执行 `sync; echo 3 > /proc/sys/vm/drop_caches`。

TrEnv-X 每轮先 sync 并清 guest cache，再调用原生 VM snapshot。由于 SDK 不提供直接按该 snapshot ID 恢复的接口，[适配器](systems/trenvx/README.md)把最新实例 writable rootfs 与内存 snapshot 组合为下一轮临时模板，并将 Cloud Hypervisor `config.json`、`state.json` 内嵌的磁盘/pmem 绝对路径改为新模板路径。临时模板在结束时清理。历史写入仍在 block upper，本实验没有 Exp3 的 checkpoint DAX 封存。

## 测量与结果

时间只计每轮动作。初始创建、轮间 checkpoint、镜像提升与恢复写入 `transitions.tsv`，不计入 workload 延迟。检查四轮共 32 步及四次 transition；oracle 检查第四轮 004 的 `type G = (A & B)[keyof C];`，并保留 Jest、最终 diff 和状态继承记录。

结果位于 `motivation/results/exp2-multi-rounds/{agentenv-preserve-cache,agentenv-drop-cache,trenvx}/`，统一比较见[结果报告](../../results/exp2-multi-rounds/summary.md)。

内存定义为 `guest used = MemTotal - MemFree`。TrEnv-X 的 `/dev/pmem0` 以 `dax=always` 映射，只读 rootfs 不属于 guest RAM；报告中的 pmem rootfs mapping capacity 是容量，不是 host 实际 RSS。guest 和 host 数据不能直接相加。
