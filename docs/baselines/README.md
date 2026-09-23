# Baseline 与修改范围

本项目使用两个本地 fork。以下差异来自子模块提交和实验脚本；固定镜像、工具及运行参数见[部署说明](../deployment/README.md)。

| 系统 | 本仓库版本 | 原有能力 | 本实验增加或调整 |
| --- | --- | --- | --- |
| [AgentENV](agentenv.md) | `6c67f92afb8e697bd4d5eb1715864119c1e10c5d`，基于 `0d9027e` | Firecracker、ublk/OverlayBD、持久 snapshot 与文件系统 CoW | free-page reporting 开关；实验外层的缓存策略、可选 Direct I/O wrapper 和测量 |
| [TrEnv-X](trenvx.md) | `53041d8c924514fca27e363cce7f5af8079267ce`，基于本地初始提交 `8bb02dc` | 定制 Cloud Hypervisor、基础镜像 virtio-pmem/DAX、私有 block upper | 多 checkpoint DAX 层、模板克隆、共享 inode 与独立 upper；实验 controller 构造和恢复历史层 |

## 各实验实际比较什么

| 实验 | AgentENV | TrEnv-X |
| --- | --- | --- |
| Exp1 | block 文件系统；可另测 host lower Direct I/O | 基础 rootfs 为只读 DAX；写入仍走 block upper |
| Exp2 | checkpoint 前保留或清除 guest cache | 基础 DAX + writable rootfs/VM snapshot 提升；历史写入仍走 block |
| Exp3 | 自然缓存、持久 snapshot/CoW；主比较关闭 balloon reporting | 基础镜像及 checkpoint 历史写入均为只读 DAX；后续写入使用新的独立 block upper |

Exp3 的 TrEnv-X 是增量 DAX 原型/实验性近似对照，不是完整的 checkpoint-native 文件系统。其模板构建开销、VM 状态语义与 AgentENV 不同，报告应明确这些条件。`virtio-pmem` 在这里映射 host 文件，不要求机器配有真实持久内存硬件；guest 绕过文件页缓存并不意味着 host 不占用 DRAM。
