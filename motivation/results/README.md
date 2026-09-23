# 实验结果

每个实验目录包含自动生成的 `summary.md`、`figures/` 和 `raw/`。`raw/<run-id>` 是
一次运行的完整原始记录；不要手工合并或覆盖不同 run。summary 和图可以随时从 raw
结果重新生成。

- `exp1-single-app-smoke/agentenv/`：AgentENV Firecracker + OverlayBD；
- `exp1-single-app-smoke/trenvx/`：TrEnv-X 定制 Cloud Hypervisor + virtio-pmem/DAX，
  并生成该实验固定 workload 的跨 runtime 对比表。
- `exp2-multi-rounds/agentenv-preserve-cache/`：AgentENV 四轮 snapshot，保留 guest page cache；
- `exp2-multi-rounds/agentenv-drop-cache/`：AgentENV 四轮 snapshot，checkpoint 前清 cache；
- `exp2-multi-rounds/trenvx/`：TrEnv-X 四轮内存 snapshot，并从最新 writable rootfs
  重建下一轮 template。
- `exp2-multi-rounds/summary.md`：上述三组 exp2 baseline 的统一 action-only 对比。
- `exp3-fork/agentenv-preserve-cache/`：AgentENV 原生四 child fork，保留 guest cache；
- `exp3-fork/agentenv-drop-cache/`：同一原生 fork，fork 前清空 guest cache；
- `exp3-fork/trenvx/`：从父状态提升一个共享 filesystem/memory COW template，再并发
  restore 四个 child；
- `exp3-fork/summary.md`：fork 后各分支时延、fault/I/O 和 guest memory/page-cache 对比。
- `exp4-realistic-fork/agentenv/`：原父延续实例与 4 个原生 fork child；
- `exp4-realistic-fork/trenvx/`：从共享 snapshot 恢复父等价实例与 4 个 child；
- `exp4-realistic-fork/summary.md`：父未预热文件 fan-out 后的 guest cache 与全 VMM 聚合
  PSS 增量对比。
- `exp5-RL-fork/summary.md`：Agent 采样的 Prettier 修复轨迹，单次 BPO 下比较
  TrEnv-X 与 AgentENV balloon 开/关的工具时延、文件内容物理峰值和 VMM PSS 峰值。
