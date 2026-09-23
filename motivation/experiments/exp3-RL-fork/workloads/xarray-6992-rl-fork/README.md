# Xarray #6992：七条冻结修复轨迹

任务、固定 commit/镜像、分支目标和验证方式见[workload 说明](../../../../../docs/workload/workload-xarray-6992.md)。

- `task.json`：任务元数据与镜像来源。
- `agent-sampling.json`：DeepSeek 采样消息、命令、退出码和输出。
- `rollouts.json`：主干、early 三分支、late 三分支及共享前缀。
- `segments/*/actions.tsv`：实际回放命令与 SHA256；只使用轨迹图引用的 segment。
- `guest-runner.sh`：逐动作执行、计时、内存采样与产物输出。
- `physical-cache-probe.py`：guest file-LRU PFN 导出，供 host 去重归因；属于测量工具，不是任务动作。
- `plan.py`：核验冻结输入，不生成新轨迹。

```bash
python3 motivation/experiments/exp3-RL-fork/workloads/xarray-6992-rl-fork/plan.py
```

七条路径共 35 个逻辑 segment；物理执行次数由 GRPO/BPO/TVCache 调度决定。保留失败探索，不以“所有动作返回 0”作为验收。两系统须重放同一 manifest 并得到一致终态 patch，聚焦测试结果另行审计。运行见 [Exp3 README](../../README.md)。
