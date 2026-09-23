# AgentENV：七分支回放适配

`run.sh <grpo|bpo|tvcache>` 校验空闲服务、balloon 配置和冻结输入，启动 VMM/PFN 采集器，再调用公共 `controller.py`。controller 冷启动时上传 workload，用 `aenv snapshot create` 保存状态，再以 `aenv start <snapshot>` 派生分支；原父实例继续运行。

主比较先执行 `set-balloon.sh off`，运行时再声明 `BALLOON_MODE=off`。只设置环境变量不会改变设备。保留自然缓存，不主动 drop cache。

必须显式设置任务的 `WORKLOAD_NAME/WORKLOAD_IMAGE` 和 `OUTPUT_ROOT`；默认输出仍为旧 `exp5-RL-fork`。完整命令见[执行与验收](../../../../../docs/deployment/experiments.md)。`fork_api.py` 是保留的辅助实现，不在当前 controller 路径中。

controller 在 `finally` 清理实例和临时 snapshot，runner 清理监测进程；异常时检查 raw 中的 ID 与 `cleanup-errors.log`。`cleanup.sh` 默认搜索旧结果根，使用前也需明确 `OUTPUT_ROOT`。
