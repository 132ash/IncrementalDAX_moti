# TrEnv-X：四轮保存与恢复适配

每轮结束后在 guest 中 sync 并清除 page cache，再调用 SDK `snapshot(delete=False)` 保存 Cloud Hypervisor 内存映像。`client.py` 将原生 snapshot 与当前实例最新的 `writable-rootfs.ext4` 组合成下一轮临时模板，修正 `config.json`、`state.json` 中磁盘/pmem 路径和模板 ID，再通过 `Sandbox.create` 恢复。

基础只读镜像使用 DAX；历史写入仍位于 block writable rootfs，不封存为额外 DAX 层。四轮结束后删除临时模板；转换耗时只作为生命周期诊断。运行命令见 [Exp2 README](../../README.md)，部署见 [TrEnv-X](../../../../../docs/deployment/trenvx-baseline.md)。
