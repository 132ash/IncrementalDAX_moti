# Exp5 BPO / agentenv / balloon on

运行：`20260918T160442Z-bpo-agentenv`；固定 trace SHA-256：`300c62abd02ce5d8dc2c7eddc41e24f8d3354d2cc0fd7395c18bb7b3bda566aa`。

- 已执行 17 个 segment、84 个工具 action；非零 exit：backbone/read_repo/002=127；派生 6 个 child。
- 工具执行时间 **42.90 s**；仅包括工具 action，不包括 checkpoint、模板构建、启动或测量。

| 全程峰值口径 | MiB |
| --- | ---: |
| **文件内容采样峰值**：guest file-LRU host PFN 去重 + DAX 文件映射 PSS | **557.8** |
| **VMM 映射监测峰值**：聚合 PSS | **2981.3** |

文件内容在每个 segment 完成后及终态逐页采样，共 18 次；最大样本来自 `host/physical-samples/018-terminal-retained/physical-memory.json`。两次采样之间的瞬时峰值可能更高。 VMM PSS 监控目标间隔为 0.1 秒，取全程观测峰（阶段 `terminal-retained`，当时 7 个 VMM）；七条 rollout 同时存活期间的峰值另为 2981.3 MiB。两个主指标峰值不要求同时发生。VMM PSS 不含 daemon、kernel 或未映射的 host 块文件缓存，不能称为全机沙箱关联内存。原始逐页探针和映射保存在 `raw/20260918T160442Z-bpo-agentenv/host/`。

在 VMM PSS 峰值样本里，匿名页 PSS 为 2461.9 MiB，文件映射 PSS 为 519.4 MiB；内存共享和已释放 guest 页的宿主驻留均影响前者。

AgentENV 在分叉点创建持久快照模板；子沙箱各有私有可写层，同模板复用只读内存快照设备。 工具动作来自 DeepSeek 对固定 Prettier 代码修复任务的一次交互式采样；正式测量回放同一冻结轨迹。它不是 RL 策略训练或在线模型推理时延测量。
