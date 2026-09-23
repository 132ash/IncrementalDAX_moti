# TrEnv-X：Prettier #14400 适配

本目录通过 TrEnv-X 高密度路径回放共同的 26 步 workload：使用固定版本的定制 Cloud Hypervisor，将共享只读 ext4 镜像作为 virtio-pmem/DAX lower，私有可写层使用 virtio-blk。

```bash
conda activate hybridfs
bash motivation/experiments/run.sh trenvx prettier-14400 setup
bash motivation/experiments/run.sh trenvx prettier-14400
```

先按[部署说明](../../../../../docs/deployment/trenvx-baseline.md)准备 host 权限并修改 `config.toml` 中的原机器 `envd_path`。

`setup.sh` 构建派生 workload 镜像、指定 Cloud Hypervisor、TrEnv-X 组件，并在缺少 CH guest kernel 时调用 `build-kernel.sh`，最后生成 snapshot 模板。已有模板时拒绝覆盖；有意重建才设置 `REBUILD_TEMPLATE=1`。

`run.sh` 启动实验专用本地 orchestrator，创建单个 sandbox，核验 pmem/DAX，采集原始数据、删除实例并更新对比报告。setup 和 run 都要求激活 `hybridfs`。

运行资产位于 `/var/lib/trenvx`，结果位于 `motivation/results/exp1-single-app-smoke/trenvx/`。源码修改与后续实验的差异见 [TrEnv-X baseline](../../../../../docs/baselines/trenvx.md)。
