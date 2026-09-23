# Exp5 GRPO / trenvx

> 旧终态口径，仅供内存归因；用户已要求峰值口径，待重测。

运行：`20260918T090001Z-grpo-trenvx`；固定 trace SHA-256：`488a574f9252bf49a70372309e6418e306b65d8a928a7f9f187fbce62dd5433d`。

- 已执行 35 个 segment、135 个工具 action；非零 exit：无；派生 0 个 child。
- 工具执行时间 **1188.98 s**；仅包括工具 action，不包括 checkpoint、模板构建、启动或测量。

| 终态七沙箱 host 物理占用 | MiB |
| --- | ---: |
| **文件缓存总量**：guest file-LRU host PFN 去重 + DAX 文件映射 PSS | **663.9** |
| **七个 VMM 映射总量**：聚合 PSS | **20940.8** |

文件缓存使用 guest `/proc/kpageflags` 标识 file-LRU PFN，经 KVM memslot 映射到 host `/proc/PID/pagemap` 后按 host PFN 去重；DAX base 和 checkpoint 文件按 `smaps` PSS 相加。总量取同次扫描的七个 VMM PSS；它不含 VMM 外的 daemon、kernel 或未映射的 host 块文件缓存，不能称为全机沙箱相关内存。原始逐页探针与映射保存在 `raw/20260918T090001Z-grpo-trenvx/host/`。

TrEnv-X 每次 checkpoint 将整个根文件系统的可写层封存为只读 DAX 层；父沙箱与子沙箱都从新模板恢复。各模板保留基础 DAX 和继承的封存层；每个模板拥有清除 guest 文件缓存后保存的独立内存快照，同一模板的实例共享该快照并使用独立块 upper。 此处是固定 Prettier 任务 replay，并非在线 RL policy 采样。
