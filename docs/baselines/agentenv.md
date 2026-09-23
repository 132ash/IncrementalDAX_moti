# AgentENV：block 与持久 snapshot 对照

AgentENV 使用 Firecracker；文件系统经 ublk/OverlayBD 提供 block 设备，文件读取会形成 guest page cache。多个恢复实例可通过同一内存 snapshot 的 CoW 映射共享已有页，fork 后新读入的文件页则可能在不同 guest 中重复存在。

## 源码修改

本地提交 `6c67f92` 只增加 **`[firecracker].free_page_reporting`** 配置：

| 文件 | 修改 |
| --- | --- |
| [config/default.toml](../../baselines/AgentENV/config/default.toml) | 默认值为 `true`，保持原有行为 |
| [src/cfg.rs](../../baselines/AgentENV/src/cfg.rs) | `FirecrackerConfig` 新增布尔字段，缺省为 `true` |
| [sandbox.rs](../../baselines/AgentENV/src/sandbox/firecracker/sandbox.rs) | 冷启动 VM 时按开关决定是否调用 `set_balloon()` |

该开关控制 virtio-balloon free-page reporting，不能理解为关闭 guest 的 DAMON/LRU 回收。原实现将 guest 回收后的空闲页报告给 host，以释放物理内存；关闭 reporting 后，guest 逻辑空闲量与 host 实际驻留量可能分离。已有 snapshot 继承创建设备时的状态，切换配置后需重新冷启动并创建快照。

Exp3 的 [set-balloon.sh](../../motivation/experiments/exp3-RL-fork/systems/agentenv/set-balloon.sh) 要求无活跃 sandbox，修改 `aenv-server` 容器内 `/workspace/config/default.toml` 后重启服务。`BALLOON_MODE=off` 只声明 runner 的预期状态并触发核验，不能替代该切换步骤。主比较使用 `agentenv-balloon-off`；历史 balloon-on 结果单独归档。

## 实验适配（位于主仓库，不属于源码补丁）

- **Exp1**：固定镜像冷启动，上传 26 步动作，默认清除 guest cache 后测量；采集服务 cgroup 和 Firecracker PSS。
- **Exp2**：用 `aenv snapshot create` 保存，再用 `aenv start <snapshot>` 恢复。`preserve` 不干预缓存；`drop` 在每次 checkpoint 前执行 `sync; echo 3 > /proc/sys/vm/drop_caches`。四轮均执行保存与恢复。
- **Exp3**：controller 用持久 snapshot 派生分支，父实例继续运行；不主动清 guest cache。当前执行路径是 snapshot + start，目录中保留的 `fork_api.py` 不是 controller 的调用路径。
- **可选 Direct I/O**：Exp1 的启动 wrapper 将 server 每次生成的 `overlaybd-global.json` 中 `ioEngine` 从 0 改为 2。只绕过 host 对本地只读 lower commit data 的缓存；guest cache、writable upper 和 index 仍按原路径工作。这不是 DAX，也不是源码新增 TOML 选项。

Direct I/O 的启用、回退和 `EXPECTED_OVERLAYBD_IO_ENGINE=2` 核验见 [AgentENV 部署](../deployment/agentenv-baseline.md)。它会影响同一服务，不能将启用前后数据混为一组。

## 解释限制

AgentENV 没有在这些脚本中为每个 sandbox 建立独立 host cgroup，所以 cgroup 的 `file` 是整个服务的计费量。runner 要求没有其他活跃 sandbox，以减少干扰；仍不能把它标成严格的单实例文件缓存。guest cache、VMM PSS 和 host block cache 应分别报告。
