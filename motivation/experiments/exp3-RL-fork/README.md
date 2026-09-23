# Exp3：三个真实修复任务的七分支回放

本实验使用 Prettier #6604，以及本地任务元数据标记难度为 `>4 hours` 的 SWE-bench Verified 任务 Xarray #6992、Sphinx #7590。DeepSeek 在固定镜像的隔离副本中根据工具输出选择命令，先采样一条主干，再从两个保存状态各采样三条延续分支。命令、输出、退出码与模型消息冻结在各 workload 的 `agent-sampling.json` 中，API key 不写入轨迹。

这是**模型采样的代码修复轨迹**，不是训练后的 RL policy。实验者指定 checkpoint 阶段和分支目标，模型决定具体工具动作；测量阶段不调用 API、不安装依赖、不运行完整测试套件。失败探索保留。任务详情见 [workload 索引](../../../docs/workload/README.md)。

## 三种调度

每个任务有七条逻辑路径，共 35 个逻辑 segment。早期状态在主干第 2 段后保存，后期状态在第 4 段后保存（包含候选修改与验证）。

| 调度 | 实际执行 | 物理 segment：Prettier / Xarray / Sphinx |
| --- | --- | --- |
| GRPO | 七个独立 root 并发执行全部路径，无中途 fork | 35 / 35 / 35 |
| BPO | 主干先执行并在线保存两个状态，主干完成后从各状态启动三个 child；六条 suffix 并发 | 17 / 17 / 17 |
| TVCache | 遍历冻结轨迹的前缀树，共同前缀只跑一次，真实分歧点保存并派生 | 13 / 17 / 17 |

Prettier 的分支额外共享 early/late inspect 段，所以 TVCache 更少执行四段。当前 TVCache 为避免全局物理探针与创建/快照竞争，**按确定顺序推进子树**；它不是完整线上并发缓存控制器。BPO 没有基于 policy entropy 自动选点，TVCache 也不模拟线上命中率或淘汰策略。

## 运行

完整的三任务环境变量、构建与成对执行命令见[部署与测试](../../../docs/deployment/experiments.md)。当前公共入口仍指向历史 `exp5-RL-fork`，本实验须直接调用本目录 `systems/*/run.sh`，并显式指定 `OUTPUT_ROOT`。

最小输入核验不需要启动 VM：

```bash
python3 motivation/experiments/exp3-RL-fork/workloads/prettier-6604-rl-fork/plan.py
python3 motivation/experiments/exp3-RL-fork/workloads/xarray-6992-rl-fork/plan.py
python3 motivation/experiments/exp3-RL-fork/workloads/sphinx-7590-rl-fork/plan.py
```

AgentENV 从固定镜像冷启动并上传 workload；TrEnv-X 将 workload 烘焙进任务专用模板，controller 还会在 root 启动时上传当前冻结 manifest。两侧固定为 2 vCPU / 4096 MiB。主比较用 AgentENV balloon reporting 关闭组；切换设备配置需先执行 `set-balloon.sh off`。

## Checkpoint 语义

AgentENV 保留自然 guest cache，使用持久 snapshot 和原生文件系统 CoW，父实例继续执行。

TrEnv-X 在 checkpoint 时 sync 并清 guest cache，保真归档整个 OverlayFS upper，将其封存为只读 ext4 DAX 层，再构建挂载完整历史层链的干净 staging VM 模板。父延续分支和 children 均恢复该模板并获得独立 upper，基础和 checkpoint 层通过相同 inode 共享。独立 tmpfs `/tmp` 单独归档恢复，不计作 DAX 层。实现与限制见 [TrEnv-X 修改](../../../docs/baselines/trenvx.md)。

因此这里比较的是持久 snapshot/CoW 与“历史文件层直接映射”的实验扩展。TrEnv-X 不能保留父 VM 任意进程状态，适用范围是当前动作边界上的文件状态继承。

## 指标与产物

- 工具计时只包裹 guest 动作；不含模型、checkpoint/DAX 模板构建、启动、传输或采样。controller 当前实际动作超时 600 s，guest 和 host 周期采样目标均为 0.1 s。
- 每个物理 segment 后及终态，guest file-LRU 页映射到 host PFN 并去重，再加只读 DAX 层映射 PSS；这一“文件内容物理量”可能漏掉段内峰值。
- VMM PSS 包含驻留 guest RAM 和映射文件，排除 daemon/kernel/未映射 host block cache；它与文件内容物理量有交集，不能相加。当前比较器仅列 AgentENV VMM PSS，TrEnv-X 总 PSS 不作跨系统比较。
- 终态保留七个实例再采样，之后 controller 在 `finally` 清理实例和 checkpoint 模板；失败清理查看 `cleanup-errors.log`。
- `compare.py` 验证段数、动作哈希、终态 patch 与失败集合，再按同名里程碑配对物理样本。并发进度可能不同，差额只是条件优化空间估计。

结果按 `motivation/results/exp3-RL-fork/<task>/<system>/<scenario>/raw/<run-id>/` 归档。三任务的 GRPO/BPO/TVCache 均有报告，见[结果索引](../../results/README.md)。每组目前一次成对运行，不能报告方差或全局平均收益。历史标题、模板名及部分默认路径中的 Exp5 对应当前 Exp3。
