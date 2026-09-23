# Exp5 内存差额定位（2026-09-18）

**历史记录**：下表和本页后续讨论来自旧的手写 Prettier 轨迹，不能代表新的 Agent 采样对比。旧 BPO balloon 开/关实验中，AgentENV 开启 balloon 的 VMM 峰值为 11,852.2 MiB，关闭时为 14,553.0 MiB，TrEnv-X 为 10,472.2 MiB；对应 raw 目录分别是 `agentenv-balloon-on/bpo/raw/20260918T141322Z-bpo-agentenv`、`agentenv-balloon-off/bpo/raw/20260918T141938Z-bpo-agentenv` 和 `trenvx/bpo/raw/20260918T092524Z-bpo-trenvx`。当前 Agent 采样实验见 [summary.md](summary.md)。

同一固定 Prettier 轨迹的 BPO 七沙箱终态：

| 指标 | AgentENV | TrEnv-X | TrEnv-X 差额 |
| --- | ---: | ---: | ---: |
| 七个 VMM 的 host PSS (MiB) | 8,765.4 | 10,328.7 | +1,563.3 |
| VMM 匿名页 PSS (MiB) | 8,343.6 | 9,905.9 | +1,562.3 |
| 文件内容 host 物理量 (MiB) | 810.8 | 604.2 | -206.6 |
| guest 逻辑已用内存 (MiB) | 2,894.1 | 1,738.9 | -1,155.2 |

这说明 **高出的 VMM PSS 几乎全部是 guest RAM 对应的匿名宿主页**，并非 DAX 层或文件缓存。TrEnv-X 的 `memory-ranges` 映射有 9,887.8 MiB `Private_Dirty`；AgentENV 的 ublk RAM 映射与匿名映射合计约 8,340.7 MiB `Private_Dirty`。TrEnv-X 的七个 guest 合计报告约 25.2 GiB `MemFree`，但曾被 guest 写过的宿主页仍留在 VMM 映射中。guest 当前逻辑已用内存比 AgentENV 少，也排除了“TrEnv-X 当时进程实际多用 1.6 GiB RAM”这一解释。

根因是运行时空闲页回收能力不同。AgentENV 冷启动时配置 `virtio-balloon` 的 `free_page_reporting=true`，其快照恢复会继承该设备状态；TrEnv-X 本次 Cloud Hypervisor `config.json` 的 `balloon` 为 `null`。所以 guest 释放 npm/Jest 等任务曾使用的内存后，TrEnv-X 的 host `MAP_PRIVATE` RAM 页仍驻留，AgentENV 可以接收 guest 空闲页报告并释放部分宿主页。此因果解释与上述匿名页差额一致；数据本身不能把每一页都归因到 balloon，运行时分配历史也有影响。

不能直接在现有 TrEnv-X 上打开 Cloud Hypervisor balloon。当前 Cloud Hypervisor 的 free-page-reporting 实现会对有文件后端的 guest RAM 调用 `FALLOC_FL_PUNCH_HOLE`；这里的文件是同模板父子共用的 `memory-ranges`。那会修改共享内存模板，破坏恢复语义。若要归一化这个运行时机制，须先实现不会改写共享模板的安全空闲页回收路径，再做独立正确性验证。

GRPO 也呈现同方向：TrEnv-X 七个 VMM PSS 20,940.8 MiB，AgentENV 15,498.6 MiB；文件内容物理量分别为 663.9 和 2,029.6 MiB。运行时 RAM 差额比 BPO 更大，与七条独立轨迹都执行构建/测试后留下宿主匿名页一致。

上述“七个 VMM host PSS”只覆盖 VMM 映射的物理工作集，**不是沙箱相关的全机物理占用**；辅助进程、内核和 VMM 外的 host 块缓存均不在其中。`memory.current` 也不能直接替代全机归因：AgentENV 服务 cgroup 在 GRPO 开始前已有约 10 GiB charge，BPO 前约 5 GiB；TrEnv-X 专用 cgroup 起始仅约 4 MiB。跨系统绝对 cgroup 值不可直接相减。文件内容物理量按 guest file-LRU host PFN 去重，再加只读 DAX 映射 PSS；后者是比例分摊口径。

证据：`agentenv/bpo/raw/20260918T035216Z-bpo-agentenv`、`trenvx/bpo/raw/20260918T085002Z-bpo-trenvx` 和两组 GRPO 的 `metrics.json`、`host/mapping-snapshots.tsv`、`host/physical-memory.json`；AgentENV 的 `src/sandbox/firecracker/instance.rs::set_balloon` 与 `sandbox.rs::start_resume`；TrEnv-X 的 `packages/shared/hypervisor/ch.go::Configure`；Cloud Hypervisor fork 的 `virtio-devices/src/balloon.rs::release_memory_range`。
