# Prettier #14400：TrEnv-X 与 AgentENV 结果分析

本文分析以下两次 accepted run：

- AgentENV：`20260914T124833Z-agentenv-replay`；
- TrEnv-X：`20260914T124731Z-trenvx-ch-dax-replay`。

两边使用相同的 26-action manifest（SHA-256
`6ea843b464f5f7ec3c081c539386593027ede2335c5309b945a9462feddceaa7`）、2 vCPU、
4096 MiB guest memory，并在 workload 前执行了 `sync; echo 3 > /proc/sys/vm/drop_caches`。
两次 replay 和 oracle 均通过。

## 1. 结论摘要

1. AgentENV 在 guest working-set 峰值时有约 **127.5 MiB page cache**，TrEnv-X 为
   **23.7 MiB**。若看整个 action 区间内 page cache 的单项最大值，则分别为
   **167.4 MiB** 和 **62.8 MiB**。
2. 以 `MemTotal - MemFree` 的近似驻留占用分桶，action 023 峰值时 AgentENV 比 TrEnv-X
   多 **135.7 MiB**，其中 page cache 差值为 **103.9 MiB**，约占该驻留差值的 76.6%。
   这与 AgentENV 的 block rootfs 使用 guest page cache、TrEnv-X 的只读 pmem lower 使用
   ext4 DAX 绕过 guest page cache 的设计一致。
3. 26-action 总时间差为 **1038.3 ms**，其中首次执行 Node/Prettier 的 action 023 单独贡献
   **742.9 ms（71.5%）**。AgentENV 在 workload 内发生 417 次 major fault，TrEnv-X 只有
   8 次；`pgpgin` 增量分别为 75,620 和 21,736。证据指向首次加载 Node/Prettier 时的冷
   文件访问是主要差异，而不是每个短 shell action 都稳定慢一倍。
4. 当前 2573.4 ms 对 1360.5 ms 的“启动/恢复”不是同类比较。AgentENV 脚本执行的是
   `aenv start --cold <OCI image>`，会在运行时解析镜像并准备新的 OverlayBD/ublk rootfs、
   启动 Firecracker；TrEnv-X 则恢复预构建的 Cloud Hypervisor snapshot。这个差值不能
   用来得出“TrEnv-X snapshot 比 AgentENV snapshot 快 47.1%”的结论。
5. 以上都是单次运行。VMM、guest kernel、snapshot 路径和 cache policy 同时变化，因此
   当前结果能说明“这两条完整管线在本次运行中的差异”，不能把全部收益单独归因于 DAX。

## 2. Guest memory breakdown

### 2.1 口径

- working set：`MemTotal - MemAvailable`，表示 Linux 对不可立即回收内存的估计；
- used：`MemTotal - MemFree`，用于下面的近似可加和分桶；
- page cache：`Cached + Buffers + SReclaimable - Shmem`；
- anonymous：`AnonPages`；
- tracked kernel：`SUnreclaim + KernelStack + PageTables + Percpu`；
- other：`used - page cache - anonymous - Shmem - tracked kernel`。

`other` 是采样字段未覆盖的剩余项，不应解释成单一内存类型。page cache 公式也包括 buffer
和可回收 slab，并不等于 `/testbed` 文件内容的精确大小。由于两侧使用不同 VMM/guest
kernel，`MemAvailable` 的水位和可回收性估计可能不同，所以 working set 不应与下面的分桶
相加；跨环境判断 page cache 时应直接比较 page cache 列。

### 2.2 Idle、working-set 峰值和结束状态

单位均为 MiB。两侧 working-set 峰值都出现在 action 023 的运行采样中。

| runtime / 时点 | working set | used | page cache | anonymous | tracked kernel | Shmem | other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| AgentENV / idle | 248.9 | 169.5 | 75.8 | 53.7 | 20.7 | 1.0 | 18.2 |
| AgentENV / action 023 峰值 | 400.8 | 347.2 | 127.5 | 65.3 | 21.4 | 1.0 | 131.9 |
| AgentENV / complete | 289.1 | 255.7 | 167.9 | 40.0 | 19.4 | 1.0 | 27.4 |
| TrEnv-X / idle | 269.4 | 159.5 | 14.8 | 50.9 | 16.9 | 1.0 | 75.9 |
| TrEnv-X / action 023 峰值 | 317.0 | 211.5 | 23.7 | 93.0 | 18.4 | 1.0 | 75.5 |
| TrEnv-X / complete | 290.8 | 205.0 | 62.9 | 44.0 | 18.8 | 1.0 | 78.2 |

峰值行的差异可进一步拆成：

| 分桶 | AgentENV - TrEnv-X (MiB) | 观察 |
| --- | ---: | --- |
| used | +135.7 | AgentENV 总驻留估算更高 |
| page cache | +103.9 | 最大的已识别正差值 |
| anonymous | -27.7 | 本次采样中 TrEnv-X 的 Node 匿名页反而更高 |
| tracked kernel | +3.1 | 差异较小 |
| Shmem | 约 0 | 基本一致 |
| other | +56.3 | 现有采样字段不足以继续可靠拆分 |

TrEnv-X 仍有 23.7–62.9 MiB page cache 并不与 DAX 验收矛盾。DAX 只作用于只读
`/dev/pmem0` lower；可写 `/dev/vda` upper、其他文件系统、buffer 和可回收 slab 仍会进入
这些计数。guest 中已经实际观察到 `/rom` 为 `/dev/pmem0`、ext4、`dax=always`。

另一个值得注意的现象是：TrEnv-X idle working set 比 AgentENV 高，但 `used` 和 page
cache 更低。这反映 `MemAvailable` 是带内核水位与可回收性判断的估算值，不适合仅凭一个
数字给不同 guest kernel 做精确内存归因。

## 3. 为什么 26 actions 在 AgentENV 中更慢

### 3.1 时间差集中在首次 Node/Prettier 加载

| action | 内容 | AgentENV (ms) | TrEnv-X (ms) | 差值 (ms) | 占总差值 |
| ---: | --- | ---: | ---: | ---: | ---: |
| 023 | 首次 `node` + `require("/testbed")` + format | 1243.0 | 500.1 | +742.9 | 71.5% |
| 024 | 第二次 Node/Prettier format | 596.1 | 517.3 | +78.8 | 7.6% |
| 025 | `git add` + `git diff --cached` | 145.4 | 83.2 | +62.2 | 6.0% |
| 020 | `git checkout` + `sed` + `nl` | 71.8 | 23.6 | +48.2 | 4.6% |
| 022 | `perl` 修改 + `nl` | 46.6 | 15.3 | +31.3 | 3.0% |
| 026 | 第二次 `git add` + diff | 60.0 | 40.7 | +19.3 | 1.9% |
| 其余 20 个 | 短命令 | — | — | +55.6 | 5.4% |
| **合计** | | **2414.5** | **1376.2** | **+1038.3** | **100%** |

action 延迟由同一份 guest runner 在 guest 内部测量；每个 action 不是一次独立的 AgentENV
或 TrEnv-X API 请求。因此这里的差异主要来自 guest 执行、文件访问、kernel/VMM 和 host
调度，不是 AgentENV CLI 往返开销。

第二次 Node 命令的差距明显缩小，说明 action 023 含有显著的一次性加载/初始化成本。
`git`、`perl` 等文件密集操作也偏慢，但数量级远小于 action 023。

### 3.2 Fault 与 I/O 计数支持冷文件访问解释

下表为 guest `/proc/vmstat` 从 action 001 前到 action 026 后的增量。这些是整个 guest 的
全局计数，不只属于 Node 进程。

| runtime | pgfault | pgmajfault | pgpgin | pgpgout |
| --- | ---: | ---: | ---: | ---: |
| AgentENV | 161,429 | 417 | 75,620 | 3,384 |
| TrEnv-X | 289,382 | 8 | 21,736 | 3,672 |

TrEnv-X 的总 page fault 更多，但绝大多数是便宜的非 major fault；AgentENV 的 major fault
约为其 52 倍，`pgpgin` 约为其 3.5 倍。结合 action 023 的 742.9 ms 差值和 AgentENV 更高
的 guest page cache，最合理的当前解释是：

- 实验在 action 前清空了 guest page cache；
- AgentENV 的 OverlayBD rootfs 通过 virtio-blk/ublk 访问，首次加载的文件页需要沿 block
  路径读入 guest page cache；
- 本轮 AgentENV 还启用了 `ioEngine=2`，只读 lower 使用 Direct I/O，因而不会由 host
  page cache 替 guest 的首次读取吸收成本；
- TrEnv-X 的共享只读 lower 通过 virtio-pmem + ext4 DAX 访问，不需要为 lower 文件再建立
  guest page cache。

这是有数据支持的强推断，但还不是单因素因果证明。两侧 VMM、kernel 和 CPU model 也不同，
当前没有 guest CPU cycles、iowait、block latency 或逐 action fault 计数，无法排除 Node
执行效率和 host 调度的贡献。另外，实验只清了 guest cache，没有统一清理 host cache；
TrEnv-X backing file 可能是 warm host cache，而 AgentENV Direct-I/O lower 主动绕过 host
cache，这使本轮更接近“各自配置的完整路径比较”，不是严格的同 cache-state 介质实验。

## 4. 为什么 AgentENV 的“启动/恢复”更慢

测得 AgentENV 为 2573.4 ms，TrEnv-X 为 1360.5 ms，差值 1212.9 ms。但两边计时对象并不
相同：

| runtime | 计时入口 | 实际语义 |
| --- | --- | --- |
| AgentENV | `aenv start --cold <OCI> --detach` | 解析 OCI/OverlayBD image，准备新的 writable rootfs 和 ublk device，创建并启动 Firecracker，等待 create API 返回 |
| TrEnv-X | `Sandbox.create(template=...)` | 从已构建 template 准备实例文件，启动定制 Cloud Hypervisor，restore snapshot 并 resume，等待 SDK create 返回 |

AgentENV 源码还把 cold create 明确分成 `resolve_rootfs`、`resolve_attached_drives` 和
`create_sandbox` 等阶段；TrEnv-X 则直接进入已有 template 的 restore 路径。定制 Cloud
Hypervisor 的 `7f1fa545` patch 会尽可能把 snapshot memory file 直接映射为 guest RAM，
减少 restore 时的 eager memory copy。这些差异都可能让本轮 TrEnv-X 更快。

现有 raw 数据只保存了端到端 duration，没有保存 AgentENV stage timer 或 TrEnv-X span，
所以无法从这 1212.9 ms 中准确算出镜像解析、ublk、网络、VMM 启动和 guest ready 各占多少。
最重要的结论不是某一阶段已经被证明慢，而是 **当前数字把 AgentENV cold boot 与 TrEnv-X
snapshot restore 混在了一张表里**。

## 5. 下一步怎样得到可归因结论

建议按以下优先级补实验：

1. 用同一 AgentENV workload 先创建 template/snapshot，再测 `aenv start <template>`；与当前
   `--cold` 分列报告，避免把 cold boot 标成 restore。
2. 补 TrEnv-X Firecracker + flat ext4 virtio-blk 组。它能帮助拆分 TrEnv-X 控制面、CH 和
   pmem/DAX 三部分影响。
3. 对每组至少随机交错运行 10 次，分别测 guest/host cold-cache 和 warm-cache；不要只在
   一边使用 Direct I/O、另一边保留 warm host cache 后把差值归因于 DAX。
4. 在 runner 中增加逐 action 的 `rusage`/CPU time、major/minor fault、block I/O 与 PSI；
   在创建路径保存 AgentENV stage timer 和 TrEnv-X tracing span。
5. 扩展 `/proc/meminfo` 采样字段，包括 `Active/Inactive`、`Mapped`、`Unevictable`、
   `KReclaimable`、`VmallocUsed` 和 hugepage 字段，以继续拆分当前的 `other`。
6. 做 N=1/2/4/8/16 并发实例实验并统计 host PSS/shared pages。单 guest page cache 的下降不
   等于已经证明整体 sandbox density 提升。

## 6. 原始证据

- [TrEnv-X raw run](raw/20260914T124731Z-trenvx-ch-dax-replay/)
- [AgentENV raw run](../agentenv/raw/20260914T124833Z-agentenv-replay/)
- [汇总表](summary.md)

本文所有数值均由上述 raw TSV 重新计算，没有把 host cgroup 数值混入 guest breakdown。
