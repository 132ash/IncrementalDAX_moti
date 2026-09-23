# TrEnv-X adapter

每轮结束后在 guest 中 `sync` 并清空 page cache，然后调用 SDK `snapshot(delete=False)`
保存 Cloud Hypervisor 内存映像。`client.py` 将原生 snapshot 文件与当前实例的最新
`writable-rootfs.ext4` 组合为下一轮临时 template，再通过 `Sandbox.create` restore。
四轮结束后删除所有临时 template；所有转换耗时只作为 transition diagnostics。
