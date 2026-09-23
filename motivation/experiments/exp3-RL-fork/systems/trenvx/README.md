# TrEnv-X：checkpoint DAX 适配

`setup.sh` 准备 Btrfs 数据卷、派生 workload 镜像、指定 Cloud Hypervisor/内核和带修改的 TrEnv-X，再生成任务专用基础模板。`run.sh <grpo|bpo|tvcache>` 启动本地后端与内存采集器，调用公共 controller。

`start-backend.sh` 开启 `TRENVX_PRIVATE_UPPER_COPY=1`。checkpoint 时将整个 upper 保真封存为只读 DAX 层；父延续分支和 children 从新建的干净 VM 模板恢复，共享基础及历史层 inode，各有独立 writable upper。`/tmp` 单独保存和恢复。详细机制与进程状态限制见[baseline 修改](../../../../../docs/baselines/trenvx.md)。

运行要求 `hybridfs` 环境、已挂载的 `/var/lib/trenvx-exp5-cow` Btrfs 卷、可用 PFN/bpftrace 权限，并且没有其他 Cloud Hypervisor VM。完整构建、路径修正和三任务测试命令见[部署](../../../../../docs/deployment/trenvx-baseline.md)与[执行流程](../../../../../docs/deployment/experiments.md)。

`WORKLOAD_NAME/WORKLOAD_IMAGE/DERIVED_IMAGE/TEMPLATE_ID` 随任务设置，`OUTPUT_ROOT` 显式指向当前 Exp3 结果目录。默认端口、cgroup、data root 仍使用历史 Exp5 约定；仅更改环境变量不足以迁移静态 `config.toml` 中的这些配置。
