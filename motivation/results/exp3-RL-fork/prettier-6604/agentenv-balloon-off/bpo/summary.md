# Exp5 BPO / agentenv / balloon off

运行：`20260919T034324Z-bpo-agentenv`；固定 trace SHA-256：`005bc0ca2a8bd772c640fd4dde943b72b8e9f3645b58345767a56fe01a7ccc7d`。

- 已执行 17 个 segment、84 个工具 action；非零 exit：backbone/read_repo/002=127；派生 6 个 child。
- 工具执行时间 **43.99 s**；仅包括工具 action，不包括 checkpoint、模板构建、启动或测量。

| 全程峰值口径 | MiB |
| --- | ---: |
| **文件内容采样峰值**：guest file-LRU host PFN 去重 + DAX 文件映射 PSS | **579.5** |
| **VMM 映射监测峰值**：聚合 PSS | **3114.7** |

文件内容在每个 segment 完成后及终态逐页采样，共 18 次；最大样本来自 `host/physical-samples/018-terminal-retained/physical-memory.json`。两次采样之间的瞬时峰值可能更高。 VMM PSS 监控目标间隔为 0.1 秒，取全程观测峰（阶段 `tool:late_3`，当时 7 个 VMM）；七条 rollout 同时存活期间的峰值另为 3114.7 MiB。两个主指标峰值不要求同时发生。VMM PSS 不含 daemon、kernel 或未映射的 host 块文件缓存，不能称为全机沙箱关联内存。原始逐页探针和映射保存在 `raw/20260919T034324Z-bpo-agentenv/host/`。

在 VMM PSS 峰值样本里，匿名页 PSS 为 2603.0 MiB，文件映射 PSS 为 511.7 MiB；内存共享和已释放 guest 页的宿主驻留均影响前者。

AgentENV 在分叉点创建持久快照模板；子沙箱各有私有可写层，同模板复用只读内存快照设备。 工具动作来自 DeepSeek 对固定任务 [prettier__prettier-6604](https://github.com/prettier/prettier/issues/6603) 的一次交互式采样；正式测量回放同一冻结轨迹。它不是 RL 策略训练或在线模型推理时延测量。
