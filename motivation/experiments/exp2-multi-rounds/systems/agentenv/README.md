# AgentENV：四轮保存与恢复适配

`agentenv-page-cache` 不在 checkpoint 前干预 guest cache；`agentenv-drop-cache` 在每轮 checkpoint 前执行 `sync; echo 3 > /proc/sys/vm/drop_caches`。两组均调用 `aenv snapshot create` 保存，用 `aenv start <snapshot>` 恢复；第四轮也执行这两个步骤。

生命周期时间只写入 `transitions.tsv` 作为诊断，不计入动作延迟。正常结束清理 sandbox 和临时 snapshot，保留 raw。完整命令见 [Exp2 README](../../README.md)，部署见 [AgentENV](../../../../../docs/deployment/agentenv-baseline.md)。
