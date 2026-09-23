# AgentENV baseline：prettier-14400

该目录保存 AgentENV 的私有启动与采集适配；固定 workload 位于同一实验的
`../../workloads/prettier-14400/`。它重放其中的 26 个 action，并提供内存采样、自动画图和
action，不调用模型、
不读取 `deepseekAPI`，也不向 sandbox 注入任何 API key。

## 一键运行

前置条件与 `docs/deployment/workload-prettier-14400.md` 相同：`aenv-server` 容器健康、
CLI 已认证、x86_64/KVM/ublk 可用，且 host 可无交互 `sudo` 读取 Firecracker
`smaps_rollup`。为避免 host 内存归因混淆，脚本要求开始时没有 active sandbox。
从空机器开始部署时，先按 [`DEPLOYMENT.md`](DEPLOYMENT.md) 完成检查。

```bash
cd /home/shao/MixFS
bash motivation/experiments/run.sh agentenv prettier-14400
```

默认流程为：固定 digest 冷启动 → 上传公共 action → 清空 guest page cache → 测量 26
步 → 下载 raw artifact → oracle → 删除 sandbox → 重建 summary/SVG。退出时也有 trap
清理 sandbox。设置 `KEEP_SANDBOX=1` 可用于调试，但不应用于正式运行。

常用覆盖项：

```bash
# 保留 guest 启动后 cache 状态
DROP_GUEST_CACHES=0 bash motivation/experiments/run.sh agentenv prettier-14400

# 指定唯一 run id（已存在时拒绝覆盖）
RUN_ID=trial-02 bash motivation/experiments/run.sh agentenv prettier-14400
```

固定镜像、资源配额、timeout 和采样周期集中在 `config.env`。结果默认写到
`motivation/results/exp1-single-app-smoke/agentenv/`。

Direct I/O 实验先执行下述实验专用部署脚本，再用预期值保护重跑：

```bash
EXPECTED_OVERLAYBD_IO_ENGINE=2 \
  bash motivation/experiments/run.sh agentenv prettier-14400
```

runner 会把实际生成的 `overlaybd-global.json` 和 `ioEngine` 写入该次 raw 结果；值不是
2 时在创建 sandbox 前失败。这里的 Direct I/O 只绕过 host 对本地只读 lower commit
data 的 page cache，guest page cache 仍然存在，writable upper 与 index 也仍为 buffered I/O。

当前 AgentENV 会在每次启动时生成 `ioEngine=0`，且没有对应的 TOML 开关。部署脚本会
备份原 ublk daemon、安装一个启动 wrapper，在 server 生成配置后将 `ioEngine` 改为 2，
重启并验证；恢复脚本会换回原二进制：

```bash
bash motivation/experiments/run.sh agentenv prettier-14400 enable-direct-io
# ... unified run command ...
bash motivation/experiments/run.sh agentenv prettier-14400 disable-direct-io
```

## 清理

正常运行自动删除 sandbox。若进程被强制终止，可按 raw 结果中记录的、经过 UUID 格式
校验的 ID 做幂等清理：

```bash
bash motivation/experiments/run.sh agentenv prettier-14400 cleanup
```

清理脚本只删除仍 active 且在本实验 raw 目录记录过的 sandbox；不删除 raw 数据、输入
action、镜像 cache 或其他 template。

## 结果口径

- `replay/steps.tsv`：每个 action 的 wall-clock latency 和退出码。
- `replay/guest-memory.tsv`：action 前/中/后 guest `/proc/meminfo`，20 ms 默认周期。
- `host/memory-samples.tsv`：AgentENV Docker cgroup 的 `memory.current`、anon/file/kernel，
  以及活跃 Firecracker 的 RSS/PSS。
- `summary.md`：由 `analyze.py` 从完整 raw runs 自动重建；包含延迟图、内存 breakdown、
  oracle 和测量限制。

guest page cache 与 host cgroup file cache 是不同层。AgentENV 没有为每个 sandbox 创建
独立 host cgroup，因此 host `file` 只能按整个 AgentENV 服务报告；脚本用“无其他 active
sandbox”的前置条件降低干扰，但不会把它伪装成严格的 per-sandbox 数值。
