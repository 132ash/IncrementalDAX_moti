# AgentENV + Claude Code + DeepSeek 最简实验部署

本文保留早期在线采样流程。当前固定轨迹实验使用名为 `aenv-server` 的 Docker 服务；Exp3 还要求本地 fork 的 balloon 开关。请先按[当前 baseline 部署](agentenv-baseline.md)构建服务，再按本文准备在线 agent。固定 replay 不需要模型 key；本文中的历史在线版本和浮动安装命令不作为当前性能实验的版本锁定依据。

本文给出一条单机、单 sandbox 的最小可复现实验路径：AgentENV 提供
Firecracker/OverlayBD 环境，Claude Code 通过 DeepSeek 的 Anthropic 兼容接口执行真实
代码仓库任务，同时保存 agent trajectory、代码改动和可选的文件系统 syscall trace。

本文以仓库内 `baselines/AgentENV` 的版本为准（撰写时 commit
`0d9027e3c4e3acb1539ff12601372b622512bf55`，2026-09-07），并在 2026-09-14
核对了上游文档。AgentENV 和 DeepSeek 的接口都可能变化；正式实验应固定 AgentENV、
Claude Code、模型名、任务仓库 commit 和 prompt。

## 1. 实验边界与产物

这条流程刻意不引入 Kubernetes、Miles 或完整 SWE-bench harness。一次运行产生：

```text
runs/<run-id>/
├── task.md
├── sandbox-id.txt
├── host-environment.txt
└── artifacts/
    ├── trajectory.jsonl   # Claude Code stream-json：消息、tool call/result、最终结果
    ├── claude.stderr.log
    ├── exit-code.txt
    ├── environment.txt    # agent/model/repo/kernel 等版本
    ├── git-status.txt
    ├── patch.diff
    └── syscalls.*         # 可选；strace -ff 的逐进程文件
```

需要先明确两类“轨迹”的区别：

- `trajectory.jsonl` 是语义级 agent trajectory，适合统计 `Read/Grep/Glob/Edit/Write/Bash`
  等工具调用及恢复会话，但不是块 I/O trace。
- `strace` 是 guest 内 syscall trace，可看到路径和读写调用，但仍不能判断一次访问命中了
  guest page cache 还是下沉到了 ublk/OverlayBD。

因此，最初的工作负载筛选可以用这两类轨迹；正式比较 block 与 DAX 时，还应采集 host
侧 ublk/块层指标，且不要把开启 `strace` 的运行时间当作性能结果。

## 2. 前置条件

AgentENV 单机模式要求 Linux kernel 6.8+ 和可用的 `/dev/kvm`。Claude Code 官方要求
至少 4 GiB 内存，因此模板下面显式配置为 4096 MiB，而不是使用 AgentENV 默认的
1024 MiB。

```bash
uname -r
test -r /dev/kvm && test -w /dev/kvm
grep -wE '(vmx|svm)' /proc/cpuinfo | head
```

若 AgentENV 运行在另一层虚拟机中，还需要云厂商或 hypervisor 开启 nested
virtualization。仅仅看到 `/dev/kvm` 文件并不能保证 KVM 真能创建 VM。

另外准备：

- `sudo` 权限；
- 可访问 GitHub、OCI registry、npm 和 `api.deepseek.com` 的网络；
- 一个单独申请、可限额/可撤销的 DeepSeek API key；
- 足够的主机内存和磁盘。并发 sandbox 数应按每个 sandbox 4 GiB 预算。

不要使用包含其他生产密钥的仓库做首次实验。Agent 运行时必然能访问注入给它的
DeepSeek key，仓库中的恶意指令也可能诱导 agent 泄露环境变量。

## 3. 启动 AgentENV

### 3.1 推荐：systemd 单节点安装

使用独立数据目录，便于实验完成后识别和清理状态。仓库内安装脚本会安装 server 和
`aenv` CLI、准备 ublk/KVM 权限，并创建 `aenv.service`：

```bash
cd /home/shao/MixFS
sudo AENV_HOME_PATH=/var/lib/aenv-mixfs \
  bash baselines/AgentENV/scripts/install.sh
sudo systemctl start aenv
sudo systemctl --no-pager --full status aenv
curl -fsS http://127.0.0.1:8000/health
```

首次正常启动会生成 AgentENV API key。执行 `aenv auth`，按提示输入 server URL 和
key；不要把 key 复制进本文或实验日志。

```bash
sudo cat /var/lib/aenv-mixfs/secrets/api-key
aenv auth
# Server URL: http://127.0.0.1:8000
# API key: 粘贴上一条命令显示的值
```

确认 CLI 与 server 通信正常：

```bash
aenv --version
aenv template list
aenv list
```

AgentENV API 本身只做认证、不加密流量；上面的监听地址应保持在 loopback 或可信内网。
跨机器部署时必须另行配置 TLS/VPN，不能直接把 8000 端口暴露到不可信网络。

### 3.2 可选：Docker 启动 server

若希望 server 本体容易移除，可以改用上游的单容器方式。`docker-setup.sh` 仍会在
host 加载并持久化 `ublk_drv`，也会写 sysctl 配置，所以它不是完全无痕的容器：

```bash
sudo bash baselines/AgentENV/scripts/docker-setup.sh
docker pull ghcr.io/kvcache-ai/aenv-server:latest
docker run -d --name aenv-server \
  --privileged --device /dev/kvm -v /dev:/dev \
  -p 127.0.0.1:8000:8000 \
  ghcr.io/kvcache-ai/aenv-server:latest
curl -fsS http://127.0.0.1:8000/health
```

这种方式还需单独安装 `aenv` CLI，然后从容器读取 key：

```bash
bash baselines/AgentENV/scripts/install-cli.sh
docker exec aenv-server cat /workspace/env/secrets/api-key
aenv auth
```

后文与 server 的安装方式无关。

## 4. 构建 Claude Code 模板

不要把 DeepSeek key 写进 Dockerfile。下面的模板只固化 Node.js、Claude Code 与常用
代码检索工具。最终切换到镜像已有的非 root 用户 `node`，这样无人值守模式不会以
root 身份运行。

```bash
mkdir -p .aenv
cat > .aenv/Dockerfile.claude <<'EOF'
FROM node:22-bookworm
USER root
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends git jq ripgrep strace ca-certificates && rm -rf /var/lib/apt/lists/*
RUN npm install -g @anthropic-ai/claude-code
RUN mkdir -p /workspace && chown node:node /workspace
ENV DISABLE_AUTOUPDATER=1
USER node
WORKDIR /workspace
EOF

aenv build .aenv/Dockerfile.claude \
  --name claude-deepseek \
  --cpu 2 \
  --memory 4096
aenv template watch claude-deepseek
```

注意：当前 `aenv build` 支持 `FROM/RUN/ENV/WORKDIR/USER`，但不支持 Dockerfile
`COPY/ADD`。任务仓库应在 sandbox 启动后 clone 或通过 `aenv upload` 导入。

先做一次模板自检：

```bash
SANDBOX_ID="$(aenv start claude-deepseek --detach --timeout 900)"
aenv exec "$SANDBOX_ID" claude --version
aenv exec "$SANDBOX_ID" node --version
aenv exec "$SANDBOX_ID" id
aenv delete "$SANDBOX_ID"
unset SANDBOX_ID
```

`npm install -g` 在这里会安装构建时的最新版。首轮跑通后，应把
`@anthropic-ai/claude-code` 改成实际记录到的精确版本号，重新构建模板；同时把
AgentENV release/commit 固定下来。

## 5. 准备真实任务

首个推荐 workload 已固定为 Prettier #14400，并提供了完整的 DeepSeek online-agent
与 Tracebench action replay 流程。实际实验优先按 companion 文档执行：

- [首个文件访问型 workload：Prettier #14400](../workload/workload-prettier-14400.md)
- [在线采样与原始轨迹准备手册](prettier-14400-online.md)

下面的 5.1–5.3 节保留为导入其他真实任务时的通用方法。

### 5.1 选择任务

最方便的起点是公开仓库中一个已关闭的真实 issue，固定到修复前 commit。为突出文件
访问而不是编译，可优先选择：

- 大仓库中的定位、跨文件一致性修改或文档/配置修复；
- 不需要下载大型依赖、不需要全量构建的任务；
- 有明确测试或人工验收标准，但测试时间明显短于代码检索时间的任务。

不要只凭任务描述认定其“文件访问占主导”。跑完后至少根据 tool call 比例和 syscall
trace 做筛选，再把满足条件的实例纳入正式实验集。

### 5.2 创建运行目录和 prompt

在 host 上为每次运行创建独立目录：

```bash
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-issue-001"
RUN_DIR="$PWD/runs/$RUN_ID"
mkdir -p "$RUN_DIR"
```

把真实 issue 原文和验收要求写入 `$RUN_DIR/task.md`。建议 prompt 明确限制外部检索，
防止 WebSearch 掩盖本地文件访问：

```markdown
在当前仓库中解决下面的真实 issue。

<粘贴 issue 原文，保留 URL/编号，但不要粘贴参考修复>

要求：
1. 只依据当前仓库内容定位问题，不使用网页搜索。
2. 先阅读和检索相关文件，再做最小修改。
3. 运行与改动直接相关的轻量测试；不要安装新依赖或执行全量构建。
4. 不提交 git commit。最终说明根因、修改文件和验证结果。
```

### 5.3 启动 sandbox 并导入仓库

```bash
SANDBOX_ID="$(aenv start claude-deepseek --detach --timeout 7200)"
printf '%s\n' "$SANDBOX_ID" > "$RUN_DIR/sandbox-id.txt"

aenv exec "$SANDBOX_ID" \
  git clone https://github.com/OWNER/REPO.git /workspace/taskrepo
aenv exec "$SANDBOX_ID" \
  git -C /workspace/taskrepo checkout FIXED_PRE_FIX_COMMIT
aenv upload "$SANDBOX_ID" "$RUN_DIR/task.md" /workspace/task.md
```

必须使用 commit hash，而不是会移动的 branch/tag。私有或本地仓库不要把长期 Git
credential 放进 sandbox；可以不执行上面的 `git clone`，改为在 host 打包后上传。直接上传目录会丢失执行位、符号
链接、时间戳和 hard link，因此需要保真时应上传一个 tar 包再在 guest 中解包：

```bash
tar -czf "$RUN_DIR/taskrepo.tar.gz" -C /path/to/parent taskrepo
aenv upload "$SANDBOX_ID" "$RUN_DIR/taskrepo.tar.gz" /workspace/taskrepo.tar.gz
aenv exec "$SANDBOX_ID" \
  bash -lc 'cd /workspace && tar -xzf taskrepo.tar.gz && rm taskrepo.tar.gz'
```

## 6. 配置 DeepSeek 并记录 trajectory

DeepSeek 当前给 Claude Code 提供 Anthropic 兼容 endpoint
`https://api.deepseek.com/anthropic`。模型别名会随服务更新；下面使用撰写时官方集成页
给出的 `deepseek-flash[1m]`/`deepseek-flash`。开始正式批量实验前应再次核对
[DeepSeek 的 Claude Code 集成页](https://api-docs.deepseek.com/quick_start/agent_integrations/claude_code/)，
并把最终模型名写入元数据。

当前 `aenv exec` 没有 `--env` 参数。为避免 key 出现在 host 的进程参数、shell history、
模板或 checkpoint 中，进入 sandbox 后用静默交互读取：

```bash
aenv connect "$SANDBOX_ID"
```

以下命令在 **sandbox 内** 执行：

```bash
cd /workspace/taskrepo
mkdir -p /workspace/artifacts
umask 077

read -rsp 'DeepSeek API key: ' ANTHROPIC_AUTH_TOKEN
printf '\n'
export ANTHROPIC_AUTH_TOKEN
export ANTHROPIC_BASE_URL='https://api.deepseek.com/anthropic'
export ANTHROPIC_MODEL='deepseek-flash[1m]'
export ANTHROPIC_DEFAULT_OPUS_MODEL='deepseek-flash[1m]'
export ANTHROPIC_DEFAULT_SONNET_MODEL='deepseek-flash[1m]'
export ANTHROPIC_DEFAULT_HAIKU_MODEL='deepseek-flash'
export CLAUDE_CODE_SUBAGENT_MODEL='deepseek-flash'
export CLAUDE_CODE_EFFORT_LEVEL='max'
export CLAUDE_CODE_AUTO_COMPACT_WINDOW='786432'

set -o pipefail
claude -p \
  --output-format stream-json \
  --verbose \
  --forward-subagent-text \
  --permission-mode bypassPermissions \
  --disallowedTools 'WebSearch,WebFetch' \
  --max-turns 80 \
  "$(cat /workspace/task.md)" \
  2> /workspace/artifacts/claude.stderr.log \
  | tee /workspace/artifacts/trajectory.jsonl
claude_status=${PIPESTATUS[0]}
printf '%s\n' "$claude_status" > /workspace/artifacts/exit-code.txt

{
  date -u --iso-8601=seconds
  claude --version
  node --version
  uname -a
  printf 'model=%s\n' "$ANTHROPIC_MODEL"
  git rev-parse HEAD
} > /workspace/artifacts/environment.txt
git status --porcelain=v1 > /workspace/artifacts/git-status.txt
git diff --binary > /workspace/artifacts/patch.diff

unset ANTHROPIC_AUTH_TOKEN
exit "$claude_status"
```

说明：

- `-p` 让 Claude Code 非交互运行并在完成后退出。
- `stream-json --verbose` 是主 trajectory；它包含结构化消息与 tool use/result。
- `--forward-subagent-text` 使较新的 Claude Code 版本把嵌套 subagent 消息也转发到
  stdout。若固定的旧版本不支持该参数，删除它并在元数据中注明。
- `bypassPermissions` 只应在隔离、一次性的 sandbox 中使用。它不会阻止网络访问，也
  不能替代低权限 API key 和可信输入。
- 不加入 `--include-partial-messages`，因为 token delta 会显著膨胀文件，且对文件访问
  分析没有帮助。
- 不依赖 `~/.claude/projects` 下的内部会话 JSONL；其格式不是本实验的数据契约。

如需继续同一会话，从 `trajectory.jsonl` 最后的 `result` 事件读取 `session_id`，再用
`claude --resume <session-id> ...`。做跨方案可比实验时不要 resume，应从同一个干净
template/snapshot 启动新 sandbox。

## 7. 导出和检查产物

回到 host 后执行：

```bash
aenv download "$SANDBOX_ID" /workspace/artifacts "$RUN_DIR/"

{
  printf 'run_id=%s\n' "$RUN_ID"
  printf 'sandbox_id=%s\n' "$SANDBOX_ID"
  printf 'agentenv_cli='; aenv --version
  printf 'agentenv_baseline_commit='; git -C baselines/AgentENV rev-parse HEAD
} > "$RUN_DIR/host-environment.txt"

tail -n 1 "$RUN_DIR/artifacts/trajectory.jsonl" | jq .
cat "$RUN_DIR/artifacts/exit-code.txt"
```

快速统计 Claude Code 显式工具调用：

```bash
jq -r '
  select(.type == "assistant")
  | .message.content[]?
  | select(.type == "tool_use")
  | .name
' "$RUN_DIR/artifacts/trajectory.jsonl" \
  | sort | uniq -c | sort -nr
```

这只能把显式 `Read/Grep/Glob/Edit/Write` 归为文件操作。`Bash` 中的 `rg/find/git/test`
也可能产生大量文件 I/O，必须结合其 `input` 和下一节 syscall trace 分析。

建议只有同时满足以下条件才把运行标记为有效：

- `exit-code.txt` 为 `0`，trajectory 最后有 `result` 事件；
- `environment.txt` 记录了 agent/model/repo 的固定版本；
- `patch.diff` 和测试结果符合任务验收；
- trajectory 中没有 API key 或其他 secret；
- 没有发生意外 WebSearch、依赖大规模下载或长时间全量构建。

## 8. 可选：采集 guest 文件 syscall trace

为了先判断工作负载形态，可以从相同 template/commit 另起一个 sandbox，把 `claude`
包在 `strace` 外层。不要在正式延迟/吞吐对比中开启它。

将第 6 节的 `claude ...` 替换成：

```bash
strace -ff \
  -ttt -T -yy -s 256 \
  -e trace=%file,%desc,%process \
  -o /workspace/artifacts/syscalls \
  claude -p \
    --output-format stream-json \
    --verbose \
    --forward-subagent-text \
    --permission-mode bypassPermissions \
    --disallowedTools 'WebSearch,WebFetch' \
    --max-turns 80 \
    "$(cat /workspace/task.md)" \
  2> /workspace/artifacts/claude.stderr.log \
  | tee /workspace/artifacts/trajectory.jsonl
```

`-ff` 会为每个进程生成 `syscalls.<pid>`。该 trace 很大，也包含 pipe/socket fd 操作；
分析时应按路径、syscall 和 fd 类型过滤。它反映的是 guest syscall，不等价于 guest
page-cache miss、块请求或物理介质访问。

若目标是评估 checkpoint/fork 后的存储路径，建议每种方案分别保存以下三个阶段的
指标：

1. 从同一只读 template/snapshot 启动后的冷运行；
2. 运行到固定语义边界后创建 checkpoint；
3. 从 checkpoint 启动一个或多个子 sandbox 后执行同一后续 prompt。

AgentENV checkpoint 和分支的最小命令是：

```bash
aenv snapshot create "$SANDBOX_ID" --name issue-001-checkpoint
CHILD_ID="$(aenv start issue-001-checkpoint --detach --timeout 3600)"

# 同节点一次 fork 多个 child；返回值是对象数组，不是纯 ID 数组。
AENV_API_KEY="$(sudo cat /var/lib/aenv-mixfs/secrets/api-key)"
curl -fsS -X POST \
  -H "X-API-Key: $AENV_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"count":3,"timeout":3600}' \
  "http://127.0.0.1:8000/sandboxes/$SANDBOX_ID/fork" | jq .
unset AENV_API_KEY
```

不要把注入过 `ANTHROPIC_AUTH_TOKEN` 的 sandbox 当成可对外分发的 checkpoint。即使
Claude 已结束且执行了 `unset`，内存或可写块中仍可能留有 key 字节。更安全的顺序是：
先在未注入 key 的任务初始状态创建 checkpoint/fork，再在每个一次性 child 中单独注入
key 和运行 Claude。若实验必须在 agent 执行中做 checkpoint，只能使用专用、限额且随后立即
撤销的 key，并把 checkpoint 当作敏感数据。

## 9. 使用已有开源 trajectory

如果第一阶段只想估计 agent 的文件操作结构，可以先下载开源 trajectory，省去模型
调用成本：

本仓库已经为 Tracebench 的 `prettier__prettier-14400` 固定了 artifact SHA256、OCI
image digest，并给出了可审计的 26-step replay runner；参见
[Prettier #14400 workload](../workload/workload-prettier-14400.md)。

- [SWE-agent trajectories](https://github.com/SWE-agent/SWE-agent/blob/main/docs/usage/trajectories.md)：
  `.traj` 中包含 thought/action/observation，并通常带对应 config 和运行日志。
- [Tracebench](https://huggingface.co/datasets/Contextbench/Tracebench)：包含 3316 条
  Terminal-Bench/SWE-bench 轨迹；大部分条目还提供 `.tar.zst` 原始 artifact，较适合
  做步骤级分析。
- [Open-SWE-Traces](https://huggingface.co/datasets/nvidia/Open-SWE-Traces)：大规模
  SWE-agent/OpenHands 消息和工具轨迹，适合统计行为分布，但不是可直接重放的块 trace。
- [SWE-smith trajectories](https://huggingface.co/datasets/SWE-bench/SWE-smith-trajectories)：
  可补充更多 SWE 风格任务和轨迹。

读取 Tracebench manifest 的最小示例：

```bash
python3 -m venv .venv-trajectory
. .venv-trajectory/bin/activate
python -m pip install datasets huggingface_hub pyarrow
python - <<'PY'
from datasets import load_dataset

rows = load_dataset("Contextbench/Tracebench", split="verified")
for row in rows.select(range(min(10, len(rows)))):
    print(row["traj_id"], row["agent"], row["model"],
          row["step_count"], row["artifact_path"])
PY
```

开源 trajectory 只能告诉我们 agent 做了什么，不能直接还原当时的 page cache、文件
布局、OverlayBD layer 或块访问序列。用于本项目时应把它当作工作负载种子：固定对应
repo/image，抽取 shell/tool action，在 AgentENV 中实际重放并重新采集 I/O。若 artifact
不含完整环境或 action 依赖 harness 私有状态，则不要声称它是可复现实验。

## 10. 清理

### 10.1 每个任务结束后

先确认产物已经下载，再删除 sandbox：

```bash
test -s "$RUN_DIR/artifacts/trajectory.jsonl"
aenv delete "$SANDBOX_ID"
unset SANDBOX_ID
```

删除 sandbox 不会删除之前创建的持久 snapshot。逐项检查并删除实验 checkpoint：

```bash
aenv snapshot list
aenv template delete issue-001-checkpoint
```

### 10.2 一批实验结束后

若之后还会运行任务，保留 `claude-deepseek` 模板，只删除 sandbox 和临时 snapshot。
完全不再需要时：

```bash
aenv list
aenv snapshot list
aenv template delete claude-deepseek
```

不要写一个不加筛选的循环删除 `aenv list` 中所有对象；同一 server 可能承载其他人的
实验。

### 10.3 停止 server

systemd 安装：

```bash
sudo systemctl stop aenv
```

Docker 安装：

```bash
docker rm -f aenv-server
```

如果使用了本文专用的 `/var/lib/aenv-mixfs`，确认 server 已停止、所有需保留的
snapshot 已导出后，才可删除该目录。安装脚本还会创建 systemd unit、二进制、用户、
ublk/网络设置；上游目前没有完整 uninstall 命令，所以“彻底卸载”最好通过恢复专用
实验机/VM 的 host snapshot 完成，而不是盲目删除 `/etc`、`/dev` 或网络规则。

Docker 路径的 `docker-setup.sh` 写入了 `/etc/modules-load.d/aenv-ublk.conf` 和
`/etc/sysctl.d/99-aenv.conf`；删除容器不会撤销这两项 host 配置。只有在确认它们没有
被其他服务使用后再人工回退，运行时 sysctl 值还需要重启或恢复到部署前记录的值。

## 11. 常见问题

### `/dev/kvm` 存在但 sandbox 启动失败

检查 nested virtualization、当前用户/`aenv` service 用户的 KVM group 权限，以及
`journalctl -u aenv`。同时确认 `ublk_drv` 已加载：

```bash
lsmod | grep '^ublk_drv'
sudo journalctl -u aenv -n 200 --no-pager
```

### sandbox 很快自动 pause

`aenv start` 的 TTL 到期默认会 pause。首次真实任务建议显式设置 `--timeout 7200`；
运行中可执行：

```bash
aenv timeout "$SANDBOX_ID" 7200
```

### Claude Code 无法访问 DeepSeek

在 sandbox 中检查 DNS/TLS 和变量名，但不要输出 token：

```bash
getent hosts api.deepseek.com
curl -I https://api.deepseek.com
printf '%s\n' "$ANTHROPIC_BASE_URL" "$ANTHROPIC_MODEL"
test -n "$ANTHROPIC_AUTH_TOKEN"
```

若出现模型不存在，优先核对 DeepSeek 当前集成页，而不是随意改回 Anthropic 模型名。

### trajectory 为空或被截断

确认使用了 `-p --output-format stream-json --verbose`，管道前启用了 `pipefail`，并检查
`claude.stderr.log` 与 `exit-code.txt`。sandbox TTL 到期、API 限额、网络中断和
`--max-turns` 都可能使任务提前结束。

## 12. 参考资料

- 仓库内 [AgentENV README](../../baselines/AgentENV/README.md)
- 仓库内 [AgentENV CLI reference](../../baselines/AgentENV/docs/src/getting-started/aenv-cli.md)
- 仓库内 [AgentENV snapshots](../../baselines/AgentENV/docs/src/concepts/snapshots.md)
- [AgentENV upstream](https://github.com/kvcache-ai/AgentENV)
- [Claude Code CLI reference](https://code.claude.com/docs/en/cli-usage)
- [Claude Code installation](https://code.claude.com/docs/en/setup)
- [DeepSeek × Claude Code](https://api-docs.deepseek.com/quick_start/agent_integrations/claude_code/)
- [SWE-bench evaluation harness](https://github.com/SWE-bench/SWE-bench/blob/main/docs/reference/harness.md)
