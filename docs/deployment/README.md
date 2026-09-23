# 部署与测试

实验运行在 Linux x86_64 主机。当前 Windows checkout 用于整理代码和文档；下列命令在有 KVM 的 Linux 实验机上、仓库根目录执行。

| 步骤 | 说明 |
| --- | --- |
| 1. [AgentENV 部署](agentenv-baseline.md) | 从本地 fork 构建 Docker server、认证 CLI、切换 balloon/Direct I/O |
| 2. [TrEnv-X 部署](trenvx-baseline.md) | 构建指定 VMM/内核、准备权限与 DAX 模板 |
| 3. [执行与验收](experiments.md) | Exp1/2/3 的测试矩阵、结果路径、正确性与内存口径 |

两侧统一使用固定 digest 镜像、2 vCPU 和 4096 MiB guest RAM。Exp3 最终保留七个实例用于采样，主机还需容纳服务、staging VM、镜像和快照。需具备：

- Linux 6.8+、可用 KVM 和 ublk、cgroup v2；Docker；可无交互执行采集/挂载所需的 `sudo -n`。
- Bash、Python 3.11+（建议 3.12）、`jq/curl/tar/zstd/flock`；TrEnv-X 另需 Go 1.23、Rust 1.85、编译工具、ACL、`cgexec`。
- Exp3 另需 `bpftrace`、host 的 `/proc/<pid>/{mem,pagemap,smaps}` 读取权限，以及 guest root 对 `pagemap/kpageflags` 的访问权限。物理页探针固定按 4 KiB 页和 4 GiB guest RAM 布局实现，不应随意更改资源配额。

```bash
test "$(uname -m)" = x86_64
test -r /dev/kvm && test -w /dev/kvm
test -f /sys/fs/cgroup/cgroup.controllers
sudo -n true
git submodule status
```

若子模块尚未拉取，在新 clone 中初始化 `baselines/AgentENV` 和 `baselines/TrEnv-X`；主仓库 `.gitmodules` 使用 SSH 地址，需要相应 GitHub 访问权限。不必对 TrEnv-X 的历史 `scripts/cgexec` gitlink 做递归初始化，host 工具按部署页准备。

服务使用本机 loopback：AgentENV `8000`；TrEnv-X Exp1/2/3 分别为 `15000/15001/15005`。测试前核对端口、子网和现有实例；同一时刻只运行一个对照组，避免后台 VM 污染内存归因。

## 在线采样与固定回放

当前自动实验是固定回放，不需要 Claude Code 或 DeepSeek key。Exp3 的 `agent-sampling.json` 已保存采样时的模型消息、工具输出和退出码。

[AgentENV + Claude Code + DeepSeek](agentenv-claude-code-deepseek.md) 保留早期在线 agent 的部署流程，用于重新采集轨迹；它的 systemd/预构建镜像路径不能直接代替当前 Docker 采集器和带 balloon 开关的源码构建。Prettier #14400 的在线采集详见[历史操作手册](prettier-14400-online.md)。在线 API 耗时与固定工具回放耗时分开报告。
