# Exp5 BPO / trenvx

运行：`20260918T160718Z-bpo-trenvx`；固定 trace SHA-256：`005bc0ca2a8bd772c640fd4dde943b72b8e9f3645b58345767a56fe01a7ccc7d`。

- 已执行 17 个 segment、84 个工具 action；非零 exit：backbone/read_repo/002=127, early_3/early_3/005=2；派生 6 个 child。
- 工具执行时间 **45.65 s**；仅包括工具 action，不包括 checkpoint、模板构建、启动或测量。

| 全程峰值口径 | MiB |
| --- | ---: |
| **文件内容采样峰值**：guest file-LRU host PFN 去重 + DAX 文件映射 PSS | **427.3** |
| **VMM 映射监测峰值**：聚合 PSS | **4511.3** |

文件内容在每个 segment 完成后及终态逐页采样，共 18 次；最大样本来自 `host/physical-samples/018-terminal-retained/physical-memory.json`。两次采样之间的瞬时峰值可能更高。 VMM PSS 监控目标间隔为 0.1 秒，取全程观测峰（阶段 `tool:read_typescript`，当时 2 个 VMM）；七条 rollout 同时存活期间的峰值另为 2442.1 MiB。两个主指标峰值不要求同时发生。VMM PSS 不含 daemon、kernel 或未映射的 host 块文件缓存，不能称为全机沙箱关联内存。原始逐页探针和映射保存在 `raw/20260918T160718Z-bpo-trenvx/host/`。

在 VMM PSS 峰值样本里，匿名页 PSS 为 187.9 MiB，文件映射 PSS 为 4323.3 MiB；内存共享和已释放 guest 页的宿主驻留均影响前者。

TrEnv-X 每次 checkpoint 将整个根文件系统的可写层封存为只读 DAX 层；父沙箱与子沙箱都从新模板恢复。各模板保留基础 DAX 和继承的封存层；每个模板拥有清除 guest 文件缓存后保存的独立内存快照，同一模板的实例共享该快照并使用独立块 upper。 工具动作来自 DeepSeek 对固定 Prettier 代码修复任务的一次交互式采样；正式测量回放同一冻结轨迹。它不是 RL 策略训练或在线模型推理时延测量。
