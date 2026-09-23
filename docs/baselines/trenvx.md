# TrEnv-X：基础 DAX 与 checkpoint DAX 扩展

实验采用 TrEnv-X 的 Cloud Hypervisor 路径：基础 `rootfs.ext4` 以只读 virtio-pmem 暴露为 `/dev/pmem0`，guest 使用 ext4 `dax=always`，私有 `writable-rootfs.ext4` 通过 virtio-blk 承载 OverlayFS upper。基础 DAX、Cloud Hypervisor 私有映射恢复和基础镜像 hard link 是所采用 baseline 的已有能力。

## 源码修改

本地提交 `53041d8` 相对 `8bb02dc` 的核心改动如下。

| 文件 | 新增能力 |
| --- | --- |
| [orchestrator/sandbox/config.go](../../baselines/TrEnv-X/packages/orchestrator/sandbox/config.go) | 将模板中的 `checkpoint-*.ext4` hard link 到每个实例；`TRENVX_PRIVATE_UPPER_COPY=1` 时用 `cp --reflink=never --sparse=always` 为实例创建独立 upper |
| [shared/hypervisor/ch.go](../../baselines/TrEnv-X/packages/shared/hypervisor/ch.go) | `ExtraPmemPaths` 将 checkpoint 层作为额外只读 pmem 设备附加到 VM |
| [template-manager/build/runtime_config.go](../../baselines/TrEnv-X/packages/template-manager/build/runtime_config.go) | 增加 `dax_layer_paths`、`base_template_id` 和 `clone-template` 模式，复用基础镜像并挂接历史层 |
| [template-manager/build/snapshot.go](../../baselines/TrEnv-X/packages/template-manager/build/snapshot.go) | 向 VM 配置传递 pmem 层并生成 `dax_layers=N` 内核参数 |
| [template-manager/build/overlay-init](../../baselines/TrEnv-X/packages/template-manager/build/overlay-init) | 挂载 `/dev/pmem1..N` 为 `ro,dax=always`，将各层 `/delta` 按新到旧排列在基础 lower 前 |

提交还包含 `scripts/cgexec` 的 gitlink，它是 host 辅助工具引用，不是 DAX 机制改动。部署应另行核验可用的 `cgexec`，不将这个引用视为 DAX 补丁。

## Exp2：提升已有实例状态

[client.py](../../motivation/experiments/exp2-multi-rounds/systems/trenvx/client.py) 在每轮结束后清 guest cache、调用 `snapshot(delete=False)`，将最新 writable rootfs 与 VM snapshot 组合成临时模板，并修正 Cloud Hypervisor `config.json`、`state.json` 内嵌的磁盘和 pmem 绝对路径。基础 rootfs、upper 与 snapshot 文件均通过 `cp --reflink=auto` 复制，模板 ID 也同步更新。下一轮从该模板启动。**这里不会把历史 upper 转成 DAX 层**；临时模板在实验后清理。

## Exp3：封存 checkpoint 为只读 DAX 层

实现位于 [controller.py](../../motivation/experiments/exp3-RL-fork/controller.py) 和 [checkpoint_dax.py](../../motivation/experiments/exp3-RL-fork/checkpoint_dax.py)：

1. 在动作边界对父实例 `sync` 并清除 guest 文件缓存，单独打包 `/tmp`。
2. 复制 writable 镜像，归档整个 OverlayFS upper，保留 whiteout、ownership、ACL 与 xattr。
3. 将归档解包到新 ext4 镜像的 `/delta`，封存为只读 checkpoint 层；沿用之前的层链。
4. 用 `clone-template` 启动干净的 staging VM，挂载“最新 checkpoint → 较旧 checkpoint → 基础 rootfs”，再生成 VM 内存模板。
5. 父延续分支和 children 均从该模板恢复，分配新的独立 writable upper；恢复单独保存的 `/tmp`。所有实例通过 hard link 引用相同只读层 inode，复用 host 文件页。

基础模板 upper 的复制可使用 reflink；Exp3 orchestrator 开启 `TRENVX_PRIVATE_UPPER_COPY=1`，实例 upper 则明确禁止 reflink，避免把可写 extent 共享算作只读 DAX 收益。运行目录使用 Btrfs，实际存储布局见[部署说明](../deployment/trenvx-baseline.md)。

## 语义与测量边界

- Exp3 保存文件系统状态并重建干净 VM 模板，**不保留父 VM 任意进程、匿名内存和打开文件状态**。这适用于当前“每个动作独立 shell、动作间以文件传递状态”的轨迹，不能当作通用进程级 fork 的等价实现。
- `/tmp` 是独立 tmpfs，单独归档恢复，不属于 DAX 层；整个 root upper（包括运行产物）都会被封存，并非只提取源码 patch。
- 镜像封存、staging VM、模板构建和恢复不计入工具计时。该流程用于估计共享历史文件内容的条件收益，不能直接给出完整 checkpoint 时延改善。
- DAX 映射容量不是实际驻留内存。Exp3 对基础镜像和 checkpoint 层的映射 PSS 计入文件内容物理量；当前跨系统比较不报告 TrEnv-X 总 VMM PSS。
