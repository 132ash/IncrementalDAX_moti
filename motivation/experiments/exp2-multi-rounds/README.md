# Exp2: four-round checkpoint/restore

本实验以 Tracebench 中已解决的 `prettier__prettier-6604` 为原型，将文件访问占主导的
代码修复过程整理为四轮有状态 replay。每轮使用不同的读取、搜索、修改和 Node/Jest
验证操作；轮末执行一次 checkpoint，下一轮从该 checkpoint restore。第四轮也执行
checkpoint/restore，以保证每轮的生命周期一致。

运行矩阵：

```bash
# AgentENV：snapshot 保留 guest page cache
bash motivation/experiments/run.sh agentenv-page-cache prettier-6604

# AgentENV：checkpoint 前在 guest 中清空 page cache
bash motivation/experiments/run.sh agentenv-drop-cache prettier-6604

# TrEnv-X：首次运行先构建固定模板
bash motivation/experiments/run.sh trenvx prettier-6604 setup
bash motivation/experiments/run.sh trenvx prettier-6604
```

测量窗口只覆盖每轮 actions。初始 sandbox 创建，以及轮间 checkpoint、镜像提升和
restore 的耗时会写入 `transitions.tsv` 供排错，但分析器明确不将它们计入 workload
延迟。结果位于 `motivation/results/exp2-multi-rounds/<system>/`。

AgentENV 直接使用其持久 snapshot（文件系统、进程状态和内存映像）。`preserve` 模式
不干预 page cache；`drop` 模式在每次 checkpoint 前执行 `sync` 和 `drop_caches=3`。

TrEnv-X 每轮先 `sync` 并清空 guest page cache，再调用原生 VM snapshot 保存内存映像。
其原生 instance snapshot 不提供可直接按 ID restore 的 SDK，因此 host 将该轮的最新
实例 writable rootfs 与内存 snapshot 组合成下一轮临时 template，再创建新 sandbox。
提升过程还会把 Cloud Hypervisor `state.json` 中内嵌的 writable-rootfs 绝对路径改为新
template 的路径。这正是“按最新修改重建镜像并创建沙箱”的实验语义；临时 template
在结束时清理。

内存报告中 `guest used = MemTotal - MemFree`；TrEnv-X 的只读 rootfs 以独立的
virtio-pmem `/dev/pmem0` 和 `dax=always` 暴露，不属于 guest RAM。报告将其作为独立的
host pmem rootfs mapping capacity 展示；该容量不是运行时 host RSS。
