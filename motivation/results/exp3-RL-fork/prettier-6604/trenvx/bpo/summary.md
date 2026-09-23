# Exp5 BPO / trenvx

运行：`20260921T080328Z-bpo-trenvx-incremental-dax`；固定 trace SHA-256：`005bc0ca2a8bd772c640fd4dde943b72b8e9f3645b58345767a56fe01a7ccc7d`。

- 已执行 17 个 segment、84 个工具 action；非零 exit：backbone/read_repo/002=127；派生 6 个 child。
- 工具执行时间 **44.35 s**；仅包括工具 action，不包括 checkpoint、模板构建、启动或测量。

| 全程峰值口径 | MiB |
| --- | ---: |
| **文件内容采样峰值**：guest file-LRU host PFN 去重 + DAX 文件映射 PSS | **411.6** |
| **VMM 映射监测峰值**：聚合 PSS | **2461.3** |

文件内容在每个 segment 完成后及终态逐页采样，共 18 次；最大样本来自 `host/physical-samples/018-terminal-retained/physical-memory.json`。两次采样之间的瞬时峰值可能更高。 VMM PSS 监控目标间隔为 0.1 秒，取全程观测峰（阶段 `terminal-retained`，当时 7 个 VMM）；七条 rollout 同时存活期间的峰值另为 2461.3 MiB。两个主指标峰值不要求同时发生。VMM PSS 不含 daemon、kernel 或未映射的 host 块文件缓存，不能称为全机沙箱关联内存。原始逐页探针和映射保存在 `raw/20260921T080328Z-bpo-trenvx-incremental-dax/host/`。

在 VMM PSS 峰值样本里，匿名页 PSS 为 2083.5 MiB，文件映射 PSS 为 377.8 MiB；内存共享和已释放 guest 页的宿主驻留均影响前者。

TrEnv-X 在 checkpoint 时封存父 VM 的 writable upper，构建继承历史层的只读 DAX lower 链，并从干净模板恢复父分支和子分支；同一历史层在所有后代中保持同一 host inode，后代各用新的私有 upper。rootfs 之外的 `/tmp` 临时状态单独捕获和恢复，不计作 DAX layer。 工具动作来自 DeepSeek 对固定任务 [prettier__prettier-6604](https://github.com/prettier/prettier/issues/6603) 的一次交互式采样；正式测量回放同一冻结轨迹。它不是 RL 策略训练或在线模型推理时延测量。
