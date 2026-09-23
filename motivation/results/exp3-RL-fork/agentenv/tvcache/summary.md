# Exp5 TVCACHE / agentenv

运行：`20260918T033742Z-tvcache-agentenv`；固定 trace SHA-256：`488a574f9252bf49a70372309e6418e306b65d8a928a7f9f187fbce62dd5433d`。

- 已执行 13 个 segment、54 个工具 action；非零 exit：无；派生 6 个 child。
- 工具执行时间 **676.89 s**；仅包括工具 action，不包括 checkpoint、模板构建、启动或测量。

| 终态七沙箱 host 物理占用 | MiB |
| --- | ---: |
| **文件缓存总量**：guest file-LRU host PFN 去重 + DAX 文件映射 PSS | **1107.1** |
| **七个 VMM 映射总量**：聚合 PSS | **8583.6** |

文件缓存使用 guest `/proc/kpageflags` 标识 file-LRU PFN，经 KVM memslot 映射到 host `/proc/PID/pagemap` 后按 host PFN 去重；DAX base 和 checkpoint 文件按 `smaps` PSS 相加。总量取同次扫描的七个 VMM PSS；它不含 VMM 外的 daemon、kernel 或未映射的 host 块文件缓存，不能称为全机沙箱相关内存。原始逐页探针与映射保存在 `raw/20260918T033742Z-tvcache-agentenv/host/`。

AgentENV 在分叉点创建持久快照模板；子沙箱各有私有可写层，同模板复用只读内存快照设备。 此处是固定 Prettier 任务 replay，并非在线 RL policy 采样。
