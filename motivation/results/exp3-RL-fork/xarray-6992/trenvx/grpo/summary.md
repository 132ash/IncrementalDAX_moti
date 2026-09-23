# Exp5 GRPO / trenvx

运行：`20260921T084249Z-grpo-trenvx-incremental-dax`；固定 trace SHA-256：`ded6d88635f349ef676b35e726a13e0a7fc14d411d618021d23f88e4eba3e9db`。

- 已执行 35 个 segment、230 个工具 action；非零 exit：backbone/read_repo/003=127, backbone/read_repo/005=1, backbone/read_repo/006=1, early_3/read_repo/003=127, early_3/read_repo/005=1, early_3/read_repo/006=1, late_2/read_repo/003=127, late_2/read_repo/005=1, late_2/read_repo/006=1, late_1/read_repo/003=127, late_1/read_repo/005=1, late_1/read_repo/006=1, late_3/read_repo/003=127, late_3/read_repo/005=1, late_3/read_repo/006=1, early_1/read_repo/003=127, early_1/read_repo/005=1, early_1/read_repo/006=1, early_2/read_repo/003=127, early_2/read_repo/005=1, early_2/read_repo/006=1, backbone/trace_index_state/001=1, backbone/trace_index_state/002=141, backbone/trace_index_state/004=1, early_3/trace_index_state/001=1, early_3/trace_index_state/004=1, late_2/trace_index_state/004=1, late_1/trace_index_state/001=1, late_1/trace_index_state/002=141, late_1/trace_index_state/004=1, late_3/trace_index_state/002=141, late_3/trace_index_state/004=1, early_1/trace_index_state/001=1, early_1/trace_index_state/002=141, early_1/trace_index_state/004=1, early_2/trace_index_state/004=1, backbone/core_patch/008=1, early_3/early_3_inspect/005=1, late_2/core_patch/008=1, late_1/core_patch/008=1, late_3/core_patch/008=1, early_1/early_1_inspect/004=141, early_2/early_2_inspect/003=1, backbone/core_verify/001=1, backbone/core_verify/002=1, backbone/core_verify/004=1, backbone/core_verify/005=1, early_3/early_3_finish/006=1, late_2/core_verify/001=1, late_2/core_verify/002=1, late_2/core_verify/004=1, late_2/core_verify/005=1, late_1/core_verify/001=1, late_1/core_verify/002=1, late_1/core_verify/004=1, late_1/core_verify/005=1, late_3/core_verify/001=1, late_3/core_verify/002=1, late_3/core_verify/004=1, late_3/core_verify/005=1, early_1/early_1_finish/004=1, early_2/early_2_finish/006=1, backbone/backbone_finish/002=1, backbone/backbone_finish/005=1, backbone/backbone_finish/006=1, late_2/late_2_inspect/002=1, late_2/late_2_inspect/005=1, late_1/late_1_inspect/004=1, late_3/late_3_inspect/001=1, late_3/late_3_inspect/003=1, late_3/late_3_inspect/005=1, late_1/late_1_finish/005=1；派生 0 个 child。
- 工具执行时间 **224.57 s**；仅包括工具 action，不包括 checkpoint、模板构建、启动或测量。

| 全程峰值口径 | MiB |
| --- | ---: |
| **文件内容采样峰值**：guest file-LRU host PFN 去重 + DAX 文件映射 PSS | **731.5** |
| **VMM 映射监测峰值**：聚合 PSS | **3066.5** |

文件内容在每个 segment 完成后及终态逐页采样，共 36 次；最大样本来自 `host/physical-samples/036-terminal-retained/physical-memory.json`。两次采样之间的瞬时峰值可能更高。 VMM PSS 监控目标间隔为 0.1 秒，取全程观测峰（阶段 `terminal-retained`，当时 7 个 VMM）；七条 rollout 同时存活期间的峰值另为 3066.5 MiB。两个主指标峰值不要求同时发生。VMM PSS 不含 daemon、kernel 或未映射的 host 块文件缓存，不能称为全机沙箱关联内存。原始逐页探针和映射保存在 `raw/20260921T084249Z-grpo-trenvx-incremental-dax/host/`。

在 VMM PSS 峰值样本里，匿名页 PSS 为 2570.3 MiB，文件映射 PSS 为 496.1 MiB；内存共享和已释放 guest 页的宿主驻留均影响前者。

TrEnv-X 在 checkpoint 时封存父 VM 的 writable upper，构建继承历史层的只读 DAX lower 链，并从干净模板恢复父分支和子分支；同一历史层在所有后代中保持同一 host inode，后代各用新的私有 upper。rootfs 之外的 `/tmp` 临时状态单独捕获和恢复，不计作 DAX layer。 工具动作来自 DeepSeek 对固定任务 [pydata__xarray-6992](https://github.com/pydata/xarray/issues/6992) 的一次交互式采样；正式测量回放同一冻结轨迹。它不是 RL 策略训练或在线模型推理时延测量。
