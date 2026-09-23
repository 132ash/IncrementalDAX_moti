# AgentENV adapter

`agentenv-page-cache` 不在 checkpoint 前干预 guest cache；`agentenv-drop-cache` 在每轮
checkpoint 前执行 `sync; echo 3 > /proc/sys/vm/drop_caches`。两者都使用 `aenv snapshot
create` 和 `aenv start <snapshot>`，并把 C/R 时间仅写为诊断数据。
