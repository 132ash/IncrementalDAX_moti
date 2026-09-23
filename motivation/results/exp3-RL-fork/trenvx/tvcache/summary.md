# Exp5 TVCACHE / trenvx

运行：`20260918T090823Z-tvcache-trenvx`；固定 trace SHA-256：`488a574f9252bf49a70372309e6418e306b65d8a928a7f9f187fbce62dd5433d`。

- 已执行 13 个 segment、54 个工具 action；非零 exit：无；派生 6 个 child。
- 工具执行时间 **676.52 s**；仅包括工具 action，不包括 checkpoint、模板构建、启动或测量。

| 旧终态物理样本与 VMM 监测峰值（不可配对比较） | MiB |
| --- | ---: |
| **文件内容终态样本**：guest file-LRU host PFN 去重 + DAX 文件映射 PSS | **605.5** |
| **VMM 映射监测峰值**：聚合 PSS | **10467.6** |

此旧运行只在终态逐页采样，文件内容数值不是峰值；仅用于分层功能审计，不纳入峰值比较。 VMM PSS 由 0.1 秒监控取峰（阶段 `terminal-retained`），两个峰值不要求同时发生。VMM PSS 不含 daemon、kernel 或未映射的 host 块文件缓存，不能称为全机沙箱关联内存。原始逐页探针和映射保存在 `raw/20260918T090823Z-tvcache-trenvx/host/`。

在 VMM PSS 峰值样本里，匿名页 PSS 为 9937.5 MiB，文件映射 PSS 为 530.1 MiB；内存共享和已释放 guest 页的宿主驻留均影响前者。

TrEnv-X 每次 checkpoint 将整个根文件系统的可写层封存为只读 DAX 层；父沙箱与子沙箱都从新模板恢复。各模板保留基础 DAX 和继承的封存层；每个模板拥有清除 guest 文件缓存后保存的独立内存快照，同一模板的实例共享该快照并使用独立块 upper。 此处是固定 Prettier 任务 replay，并非在线 RL policy 采样。
