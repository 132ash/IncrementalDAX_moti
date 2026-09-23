# 面向 Agent Sandbox 的 Checkpoint-Native 直接映射文件系统

# 问题背景

* Agent特征

  * sandbox包含基础镜像、依赖、工具生成的文件、安装结果和中间产物。
  * 包含大量文件读写操作

  * Agent沙箱在执行过程中不断checkpoint。并可能从某个 checkpoint 派生多个后续 sandbox。

* 更高效的面向agent沙箱的文件系统
  * 支持快速C/R
  * 支持fork COW
  * 高效文件读写
  * 提升文件共享能力，减少内存占用（page cache）
* 两种主要方式：block，pmem DAX
  * block：多层的块结构。方便做C/R
    * checkpoint时，将当前写层变为只读。然后增加一个新写层
    * 访问时从上往下查找：块内容可能分布在多个layer中
    * 访问路径：Guest FS $\to$ Guest page cache $\to$ （miss）ublk $\to$ OverlayBD layer lookup $\to$ file content
    * 灵活但开销可能较高，依赖page cache。
  * pmem： 固定一块内存，直接映射
    * 将rootfs转换为一个ext4直接映射文件，作为host mem映射到guest物理地址
    * 访问：Guest FS $\to$ （DAX mapping）$\to$ host mem backing
    * 无page cache，多个沙箱可以映射同一个只读文件
    * 较快但是不灵活，需要预先转换/准备层

# 已有工作

* AgentENV：基于OverlayBD的blk fs

  * C/R：增量式的block

  * 降低占用

    * 通过Direct I/O去掉双重缓存
    * remote storage/lazy loading

  * 本质还是块访问路径

    * Direct I/O 避免 host 侧额外 page cache，但 **guest page cache 仍然存在**。
    * 未命中则走冷路径

  * fork出的子沙箱可以通过内存映像共享guest page cache

    * 需要文件内容被打入内存映像，重复存储/增大镜像大小
    * 不覆盖冷文件，可能被驱逐

* TrEnv-X：混合挂载virtio-pmem和blk，直接映射（DAX）

  * 基础镜像转换为只读ext4文件，映射进guest memory。可写层基于blk

  * 只读层读取时不需要经过块路径

    * Guest FS $\to$ （DAX mapping）$\to$ host mem backing
    * 无guest page cache，共享一份host物理内存

  * 文件系统布局静态配置，只有一开始的镜像在手动转换后共享

    * TrEnv-X将整个镜像制作为ext4文件，不同VM的相同层也无法复用

# insight

* TrEnv-X的方式只能共享一开始的只读镜像
  * 对于guest修改/新创建的文件：都位于私有的blk块设备可写层
  * 假设修改base中很多文件（大量代码编辑）、构建产物多，都回归块路径
  * 只能通过打包guest page cache进内存映像的方式共享
  * **能不能让后续在blk中的内容也通过DAX的方式访问？**
* Checkpoint同时也是“不可变边界”
  * 之前的层被封为只读，不可变
  * 我们可以将这些只读层采用直接映射的方式


# 我们的做法

* 目标设计（Checkpoint时）
  * Checkpoint时，将被封为只读的层提升为DAX方式
  * 恢复后映射到host mem，可写层仍然采用新blk
  * host只保留一份物理内存，fork出的子沙箱也直接映射共享
* 好处
  * 内存映像/内存占用小：不包含page cache，文件内容自动共享。不论冷/热文件
  * 访问快：不包含page cache hit/miss，都走DAX路径

* 技术要求
  * 需要增量/异步地将blk内容转化为DAX，通过改变映射/改变metadata等方式。不能copy后重新构建，阻塞关键路径
  * 块在多个物理layer上，需要将layered lookup 的结果转化为可直接建立映射的 extent map
  * 层数多了之后不能持续增长访问成本，需要merge等方式

# 问题

* 优化空间？
  * 单纯减少page cache：Trenv-X中可减少10~48%
    * 和workload形态相关

## 真实场景收益调研（2026-09-16）

* 完整调研见
  [`docs/deployment/真实Agent负载与增量DAX收益调研.md`](deployment/真实Agent负载与增量DAX收益调研.md)。
* Tree-GRPO/stateful MCTS、Best-of-N test-time scaling 与 AgentENV reward judging
  的 fork 行为、证据边界和对应实验协议，单独整理于
  [`docs/deployment/RL树搜索、Best-of-N与Reward-Judging的Sandbox-Fork行为调研.md`](deployment/RL树搜索、Best-of-N与Reward-Judging的Sandbox-Fork行为调研.md)。
* 真实 Claude Code/Codex trace 中，显式 file read/search 和 write/edit 占 tool calls
  9.3%/10.4%；再加上 shell 中严格可识别的查看文件命令，文件操作下界为
  58.0%。direct file read/search 的 0.58% tool-time 只是显式工具时间，严重漏算了
  test/build/package install 内部的文件 I/O，不能当作 DAX 上界。TVCache 的
  terminal-bench 实测中，包含 build/test 的 tool execution 平均占 rollout 43%。
* SWE agent RL 的公开配置常见每任务 8–32 条 rollout，并发 sandbox 可达
  184–512。常规 GRPO 在算法上独立采样，但 TVCache 证明执行层可对相同
  stateful tool prefix 返回缓存结果，并从 longest-prefix sandbox snapshot
  fork/copy 后只执行分叉后缀。因此“从原 prompt 开始采样”与“从中间文件状态
  fork”可以同时成立，这是增量 DAX 相对 base-DAX 的直接 use case。
* 但 fork 不能等同于“普通 GRPO 主 rollout 普遍中途分叉”。当前有三类真实价值：
  * [Kimi K3 技术报告](https://github.com/MoonshotAI/Kimi-K3/blob/main/k3_tech_report.pdf)
    明确说 AgentENV 从原 sandbox 精确状态 fork reward-judging
    sandbox，避免评分的副作用影响原轨迹；这是生产中已使用的轨迹末端 fork。
    更具体地，fork 主要适合必须执行 final environment 的 judge：hidden test、build、
    性能测试、源码检查以及启动/交互生成应用。judge child 的文件、进程、缓存和应用状态
    修改被丢弃，source 可继续 partial rollout、接受 public feedback、供其他 judge 从
    同一状态评分或留作审计。K3 没有公开 controller 伪代码；“每次提交都 fork”只是
    AET public/hidden verifier 语义下的合理实现推断。纯文本 Agentic GRM 和单次 terminal
    test 并不天然需要 fork。
  * TVCache 在工具前缀缓存命中后从中间 snapshot 派生分叉 suffix；这是执行层
    中途 fork。
  * BPO 在一条 backbone 的高熵 action 点，把历史 backbone action 作为第 1 个 sibling，
    额外派生 `K-1` 个 suffix；这是算法级中途 snapshot/restore，但仍是无公开代码的
    arXiv v1，不是当前 GRPO 默认形态。
  K3 只披露训练/评估总共创建 51,219,741 个 sandbox，没披露 fork 比例或
  fan-out 分布；因此可以说“fork 有真实重要用例”，不能说“多数 rollout 会中途 fork”。
* TVCache/BPO 之外的最新证据进一步支持“分层而非给单一 fork rate”：
  * RollArt 有生产 `env.reset/env.step` trace，显示数百至数千独立环境的长尾和故障，
    但全文没有 sandbox fork/snapshot；普通 RL infra 的主路径仍是 reset/step。
  * Crab 对 SWE-bench、Terminal-Bench 各 100 个可成功任务重放完整 agent trace，
    70–87% turn 无需 checkpoint；Claude-code 约 5% turn 需 FS checkpoint、8% 需
    full checkpoint。这给出 checkpoint candidate 率，不给 fork child 数。
  * DeltaBox 重放 24 条 SWE-bench MCTS trajectory，确实在 parent node checkpoint、
    向新 leaf restore；其 RL `N=1/4/16/64` 是系统 microbenchmark sweep，不是生产分布。
  * AMAP Tree-GRPO 只共享逻辑对话/tool prefix；更早的 SEEA-R1 同名算法虽在
    ALFWorld 做 MCTS+GRPO，也未公开 simulator/sandbox snapshot。ProRL Agent、RollPacker
    和 Kubernetes Agent Sandbox RL 当前也是独立 job/warm-pool/reset，不能算作中途 VM fork。
  * Daytona、CubeSandbox、Together 等提供 fork/clone API 只证明能力，不证明请求比例。
  截至 2026-09，仍无公开数据集同时包含
  `timestamp/op/parent/checkpoint/reason/child_count/lifetime`，更没有 join 后的 page/extent
  first-touch。因此真实 fleet 平均 gain 仍不可辨识。
* 按生命周期看，目前可能发生 fork/C/R 的时点应分为：
  * rollout 前的 warm-root fan-out：最常见，但很多系统只是 fresh create/warm pool；
  * 等待 LLM 或跨 iteration：K3 使用 pause/resume，不是 fork；
  * 相同工具前缀后：TVCache 从 longest-prefix snapshot 派生 suffix；
  * tree-search parent node：DeltaBox/MCTS restore 后扩展新 leaf；
  * 高熵 action 点：BPO 主动产生 sibling；
  * 中间提交或轨迹终点评分前：K3 式 verifier/reward-judge isolation；
  * 定期容错：snapshot/restore，通常不产生并存 child。
* 对当前 AgentENV，主内存收益近似为
  `(n-1) × 后代间重叠率 × fork 后共同冷只读页`。在没有生产 `mincore`/extent
  trace 之前，对 RL warm-clone 更可辩护的估算是 host 实际物理内存降低
  10–30%、完整 RL step 时间改善规划区间 0–10%。Exp4 的 37.3% PSS 增量与 76.2%
  冷读 critical-path 降低应定位为高重叠冷读上界点。

# moti实验
* 目的：验证在文件读写占主导/多分支fork/复杂任务中，使用基于pmem的直接映射相比现有工作理论的gain有多少
* baseline
  * AgentENV: 纯block文件系统，存在guest page cache
  * Trenv-X like: 将初始镜像作为pmem只读层映射，其余使用block
  * Oracle：所有只读层都使用pmem
* workloads
  * 文件读写主导：大量文件读写的真实agent任务，计算少
  * sandbox 派生场景需分类，不再统称为“RL rollout 中途 fork”：
    * 普通 GRPO root fan-out：作为无中途 fork 的对照组；
    * Kimi K3 式 reward-judge fork：轨迹末端从精确状态派生评分环境；
    * TVCache 式 tool-prefix fork：build/test 后 snapshot，命中 longest prefix 后只跑 suffix；
    * BPO 式 branch-point fork：轨迹中高熵点以 `K=4` 比较 4 个 sibling action，其中只有
      `K-1=3` 条是从历史 state 新启动的 suffix。
  * 复杂任务：包含环境构建、代码修改、测试等完整的修复任务
    * 较复杂
* 实验流程
  * 先部署AgentENV，使用Claude Code + deepseek API，跑通文件读写主导任务
    * 保存Trajectory/或者直接利用现有的Trajectory

## 缺少生产 fork trace 时的实验方法

fork 是 RL/controller 的外生决策，文件系统不需要回答“什么时候应该 fork”。
在没有生产分布时，实验目标应从“给出一个真实平均 gain”改为两件事：

1. 测量系统对给定 fork 形状的条件收益函数；
2. 使用已公开的外部策略作为场景锚点，而不自称它们是生产分布。

可将单次 fork event 表示为：

```text
S = (reason, fork_point, n, resident_at_fork, suffix_read_set,
     child_overlap, snapshot_lifetime, reclaim_state)
```

最终报告给定 `S` 时的 baseline cost `Cbase(S)` 和可加的绝对节省
`ΔC(S)=Cbase(S)-Cdax(S)`，而不是脱离 `S` 报一个全局百分比。未来获得生产分布
`P(S)` 后，才能计算：

```text
ExpectedSavedCost = ΣS P(S) × ΔC(S)
RelativeGain      = ExpectedSavedCost / [ΣS P(S) × Cbase(S)]
```

### 三层实验

#### 1. 机制层：保留 Exp4，但只用于校准上界和 break-even

控制变量扫描：

- child 数 `n=1/2/4/8/16`；
- fork 时文件页是热、自然老化后部分冷、或在 guest 内存压力下被回收；
- 后缀的共同只读集和私有集大小；
- snapshot 存活时间和同时存活的前缀节点数。

这一层可以人工控制 overlap，但结论必须标记为 mechanism/break-even，不是真实
workload。不应使用 `drop_caches` 伪造生产状态；应用默认 DAMON/LRU、可控内存配额与
真实时间间隔产生驱逐。

#### 2. 场景层：由外部策略决定 fork，文件系统只被动执行

| 场景 | fork 规则 | 建议参数 | 意义 |
| --- | --- | --- | --- |
| Vanilla GRPO 对照 | 所有 rollout 从 root template 启动，无中途 fork | `R=8/32` | 分离 base-DAX 与增量 DAX |
| K3 reward judge | agent 结束后从最终 sandbox 状态派生 judge | `n=1/2/4` 敏感性 | 最强生产证据，但 fan-out 未公开 |
| TVCache tool prefix | 由 TCG longest-prefix match 和 selective-snapshot policy 决定 | `R=4/8` | 实际 fork 点由工具历史产生 |
| BPO branch point | 由 policy entropy 选点；必须明确历史 top-M state 是逐步保存、online 保留还是 replay | 以 `K=4,M=4` 作论文锚点，扫 `K=2/8`；并发 child 按每点 `K-1` 计 | 算法级中途 C/R；论文的 compute matching 算术不自洽，不沿用其未说明的 sub-sampling |
| DeltaBox/MCTS replay | tree controller 在 parent node checkpoint，选择新 leaf 时 restore | 先用论文 30 iterations；fan-out 扫 `1/4/16/64` 仅作敏感性 | 真实代码搜索轨迹锚点，不冒充生产 RL 分布 |
| Crab selective checkpoint | turn 后有 FS/process side effect 才保存；只读 turn 跳过 | 以论文约 13–30% stateful-turn 区间校准 | checkpoint candidate 上界；本身不决定 child 数 |

场景层不要人工指定“理解完成后 fork”之类主观时刻。对 TVCache/BPO，直接运行
或重放 controller 输出的 fork event。对 reward judge，固定在 agent 交付结果、运行隐藏评分前
fork，这是由评分协议决定的时刻。

#### 3. Trace 层：同时保留隔离实验和端到端实验

- **paired trace replay**：先记录一次 controller 的 fork/checkpoint 事件和 agent tool
  trajectory，然后在 AgentENV、base-DAX 和 incremental-DAX 上重放完全相同的事件序列。
  这能隔离文件系统差异，避免三组运行产生不同 fork 决策。
- **online end-to-end**：controller 在三个系统上各自实时运行，捕获系统时延对并发命中、
  straggler 和 fork 时机的反馈效应。

两类结果不能混在一张表：paired replay 回答“同一 fork trace 下文件系统带来什么”，
online 回答“整个 RL/controller 系统最终快多少”。

### 核心指标和报告规则

每个 fork event 至少记录：

- `reason/fork_point/parent/children/checkpoint_id`；
- fork 时的 guest resident file pages，以及 base/checkpoint layer 归属；
- child 的 first-touch extent、union/intersection/Jaccard 和 refault bytes；
- fork/restore 时延、VMM PSS 增量、GiB·s memory integral 和单机可承载 sandbox 数；
- judge/rollout critical path 及同步 batch 的最慢 child；
- snapshot 存活时间、DAMON/LRU reclaim 与再读数据。

主结果应是一张条件收益表或曲线，例如 `Gain(n, cold_bytes, overlap, lifetime)`，
并报告增量 DAX 的 break-even 条件。没有 `P(S)` 前，不对外声称单一“真实平均 gain”。

### 调研时提出的后续实验方向

1. **Reward-judge fork**：复用真实 SWE/terminal agent trajectory，在最终状态 fork
   `1/2/4` 个 judge，运行隐藏测试、build 和源码检查。这是最有生产依据的场景。
2. **TVCache-prefix fork**：实现最小 TCG/LPM controller，用 `R=4/8` 的真实 tool
   trajectory 自然产生 fork 点，对比 paired replay 和 online 结果。
3. **MCTS checkpoint replay**：优先复现 DeltaBox 的 SWE-bench parent-node
   checkpoint/new-leaf restore 事件序列，并用 Crab 的 stateful-turn 分类排除无状态
   checkpoint。这比人为指定中间 fork 点更接近真实代码搜索。
4. **BPO fork**：在确实需要评估算法级 tree rollout 时再做；先补齐历史 top-M state
   的保存/replay 语义，区分总 returns 与同时活动 sandbox。它不应作为当前
   incremental-DAX 动机的唯一支撑。详细证据审计见
   [`RL树搜索、Best-of-N与Reward-Judging的Sandbox-Fork行为调研.md`](deployment/RL树搜索、Best-of-N与Reward-Judging的Sandbox-Fork行为调研.md)。

## Exp3 局限与 Exp4 realistic fork

* Exp3 从已经完成两轮检索、Node 和 Jest 操作的父 sandbox fork。fork 点的 guest page cache
  已覆盖大量后续文件；多个 child 通过同一 memory snapshot 的私有 COW 映射共享这些热页，
  因此 AgentENV preserve-cache 与 TrEnv-X 的 action 时延基本持平。
* 这不是对 motivation 的否定，而是“从充分预热父实例派生、且后续复用热文件”这一边界条件。
  真正能区分 block guest cache 与 DAX backing 的是 fork 后首次触达、但多个分支重复读取的文件。
* [`exp4-realistic-fork`](../motivation/experiments/exp4-realistic-fork/README.md) 固定以下协议：
  * fork 前只做轻量元数据访问和 checkpoint 状态创建，不读 `src/tests/node_modules` 目标语料；
  * fork 后保留 1 个父延续分支和 4 个 child，5 个 peer 首先并发读取完全相同的冷文件集合；
  * AgentENV 原父实例正常继续；TrEnv-X 从同一 snapshot 恢复父等价实例和 4 个 child，准备
    时间不计入 workload；
  * 不使用人为 `drop_caches`；COW 分开统计 fork 时公有 cache 和各 guest 的私有 cache，DAX
    分开统计宿主机 `rootfs.ext4` 实际驻留页与各 guest 的私有 writable cache，再与 5 个 VMM
    的聚合 PSS/PSS anon/PSS file 增量比较；
  * 冷读后保持 5 个实例存活再采样，避免销毁过程污染内存结论。
* 预期：AgentENV 对父未读文件在每个 guest 内建立私有 page cache；DAX 文件仍共享同一 host
  backing。因此 fan-out 越大，AgentENV 的 guest-cache 与聚合 PSS 增量增长越快，而 DAX
  主要增长共享 backing 的一份物理页。
* Exp4 当前比较 AgentENV 与“初始镜像使用 DAX”的 TrEnv-X 上界。checkpoint 后新增/修改
  内容仍位于 block writable layer；要完整验证本文设计，还需补充“checkpoint 历史只读层均
  提升为 DAX”的 Oracle baseline。

### Exp4 page-cache 归因重跑结果（2026-09-15）

* 两组使用相同 manifest、2 vCPU / 4096 MiB、5 个并发 peer；每个 peer 在 fork 后读取相同
  的 34164 个文件 / 198.9 MiB，5 条状态继承与隔离 oracle 均通过。
* AgentENV 在 fork 点有一份约 159.0 MiB 的 guest 逻辑公有 cache（目标 corpus 的 `mincore`
  驻留子集为 27.0 MiB），由 5 个 VMM 的同一 ublk memory backend 承载；lazy restore 不保证
  基线页都已在宿主 DRAM。冷读不产生新的公有层，而是在 5 个 guest 中产生 +1407.7 MiB 目标私有 cache 和
  +94.9 MiB 其余私有 cache，实际 page-cache 增量合计 +1502.6 MiB。
* TrEnv-X 的共享 DAX rootfs 冷读前驻留 19.1 MiB，冷读只新增一份 +367.0 MiB DAX 驻留页；
  5 个 guest 的私有 writable/block cache 合计新增 +124.5 MiB，实际 page-cache 增量合计
  +491.5 MiB，比 AgentENV 低 67.3%。
* 5 个 VMM 的聚合 PSS 增量分别为 +2053.7 MiB 与 +1287.1 MiB；扣除上述可归因 page cache
  后仍有 +551.1/+795.6 MiB。这些是 guest 匿名工作集、页表与 VMM/runtime fault-in 等，
  不再用 `PSS_Anon` 冒充 page cache。
* 冷读 critical path 分别为 18.849 s 与 4.495 s，TrEnv-X 降低 76.2%；进入已热的
  divergent round 后，aggregate 差距缩小到 11.9%。
* 结果支持 motivation 的限定版本：DAX 的主要收益出现在“父未预热、fork 后多个实例重复
  读取”的文件集合；exp3 的父级热 cache 确实会掩盖该收益。完整数据见
  [`motivation/results/exp4-realistic-fork/summary.md`](../motivation/results/exp4-realistic-fork/summary.md)。
* 在真实负载映射上，Exp4 更接近 TVCache/BPO 的“中间快照后多 suffix”或多个
  reward judge，不代表仅从同一 root template 独立启动的普通 GRPO。K3 没有公开
  judge fan-out，TVCache 也没有公开 LPM snapshot-resume rate；BPO `M=4,K=4` 的 13 个
  returns 也不等于 13 个并发 sandbox。所以当前 `n=5`、
  冷页重叠近 100% 仍应视为上界形状，不是已知生产分布。
* 以上是各 baseline 一次完整重跑。跨系统绝对时延还受到 VMM、snapshot、rootfs 与 host
  cache 状态影响；共享物理页使用 mapping PSS，不使用会重复计算共享页的 RSS。

## Exp5：七条 RL rollout 形状的条件收益（2026-09-18）

[`exp5-RL-fork`](../motivation/experiments/exp5-RL-fork/README.md) 已构造固定版本的
Prettier 任务七条脚本轨迹与 GRPO/BPO/TVCache 调度，包含真实源码读取、构建和 Jest。
轨迹不是采集自线上 agent 或 RL policy。严格分层协议现已实现：TrEnv-X 封存**整个**
根可写层为只读 DAX 层，让父子从同一份清除 guest 文件缓存后的 checkpoint VM 内存模板
恢复，并为每个实例分配独立 upper。BPO、GRPO、TVCache 的功能轨迹均已通过；旧终态
内存数字只用于 [`内存差额归因`](../motivation/results/exp5-RL-fork/memory-diagnosis.md)。
BPO 已按每段文件内容物理采样最大值与全程 VMM PSS 监测最大值重测 AgentENV balloon
开/关两组，并与 TrEnv-X 对比；详见 [`Exp5 BPO 峰值比较`](../motivation/results/exp5-RL-fork/summary.md)。
GRPO 和 TVCache 暂未按此口径重测。
