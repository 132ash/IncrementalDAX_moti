# 首个文件访问型 workload：Prettier #14400

本文把 [AgentENV + Claude Code + DeepSeek 部署](./agentenv-claude-code-deepseek.md)
中的泛化流程收敛为一个具体任务，并提供两种运行方式：

1. **online-agent**：让 Claude Code 使用 DeepSeek API 自主完成任务，记录新的
   `stream-json` trajectory；
2. **trace-replay**：不调用模型，顺序执行一条开源 trajectory 中已经记录的 shell
   action，以固定 agent 决策并隔离文件系统性能。

两种方式使用同一个 AgentENV snapshot 作为起点。它们分别回答“真实 agent 端到端
表现如何”和“固定文件操作序列在不同文件系统上表现如何”，不能把两者的绝对耗时
直接互相比快慢。

## 1. Workload 选择

选择的实例是 `prettier__prettier-14400`，对应 Prettier 的真实修复
[Format `<script>` inside SVG #14400](https://github.com/prettier/prettier/pull/14400)。问题要求
定位 HTML parser 对 SVG `<script>` 内容的错误格式化，并做一个很小的跨语言嵌入判断
修复。

使用的开源轨迹来自
[Contextbench/Tracebench](https://huggingface.co/datasets/Contextbench/Tracebench)：

| 字段 | 固定值 |
| --- | --- |
| Tracebench `traj_id` | `miniswe-OpenAI__GPT-5-prettier__prettier-14400-477c8cff` |
| agent / 原模型 | mini-SWE-agent 1.17.3 / GPT-5 |
| 轨迹格式 | `mini-swe-agent-1` |
| action 数 | 26 |
| Tracebench 标记 | `solved=true`、`exit_status=Submitted` |
| 环境 | `ghcr.io/timesler/swe-polybench.eval.x86_64.prettier__prettier-14400` |

对 artifact 内 26 个 assistant action 逐项检查后的分类为：

| 类别 | action 范围 | 数量 | 典型命令 |
| --- | --- | ---: | --- |
| 导航、搜索、源码读取 | 1–15 | 15 | `ls`、`nl/sed`、`rg`、`grep` |
| 修改与修改后复查 | 16–22 | 7 | patch、`sed/perl`、`git checkout`、`nl` |
| 轻量功能验证 | 23–24 | 2 | `node -e` |
| 提交与 diff 输出 | 25–26 | 2 | `git add`、`git diff --cached` |

因此按 action 数计，24/26（92.3%）直接围绕仓库文件，只有 2/26（7.7%）用于计算型
验证；轨迹中没有安装依赖、全量构建或完整测试套件。这个比例只证明它是一个合理的
首个候选，不代表 92.3% 的 wall time 或 block I/O 都来自文件访问。正式实验仍需用
guest syscall 与 host ublk/块层计数验证。

这个实例还有三个实际优点：

- 公开镜像已经包含 `/testbed`、`node_modules` 和所需工具，不必在测量窗口内安装依赖；
- 任务只修改很少的源码，适合观察“大量查找/读取，少量写入”的 agent 模式；
- 开源轨迹包含原始 action/observation，可审计后进行 action-level replay。

## 2. 固定输入

以下版本在 2026-09-14 核对过。不要在正式数据中使用浮动的 `latest`：

```bash
export WORKLOAD_NAME=prettier-14400
export TRACE_REPO_COMMIT=7da2e4f45b330be8b6e8f1cff835247723cb3341
export TRACE_ARCHIVE=miniswe-OpenAI__GPT-5-prettier__prettier-14400-477c8cff.tar.zst
export TRACE_SHA256=205c04ee98c69b1d9a6a9ef9639ff9d5ce5ae7fa36675f2404e2c4660fba8528
export WORKLOAD_IMAGE=ghcr.io/timesler/swe-polybench.eval.x86_64.prettier__prettier-14400@sha256:e625c9b9776870e2cc87172e886bbc90cfc3d6ce1521492f113a46b3f6dfcf44
export AGENT_NODE_VERSION=22.23.2
export CLAUDE_CODE_VERSION=2.1.236
```

镜像是 `linux/amd64` 单架构镜像。arm64 host 不能把它当作本实验的等价原生 workload；
通过模拟运行会引入不可忽略的额外开销。
执行前先检查 host 架构和本文使用的工具：

```bash
test "$(uname -m)" = x86_64
for tool_name in aenv curl jq python3 sha256sum zstd tar; do
  command -v "$tool_name" >/dev/null || { printf 'missing: %s\n' "$tool_name"; exit 1; }
done
```

可以用只读命令再次确认 registry 中的 digest：

```bash
docker buildx imagetools inspect \
  ghcr.io/timesler/swe-polybench.eval.x86_64.prettier__prettier-14400:latest
```

若 `latest` 已经指向其他 digest，实验仍使用上面固定的 digest。若固定 digest 已无法
拉取，应记录为输入失效，而不是静默改用新的 `latest`。

## 3. 下载并审计开源 trajectory

在 MixFS 根目录执行：

```bash
export WORKLOAD_ROOT="$PWD/runs/workloads/$WORKLOAD_NAME"
mkdir -p "$WORKLOAD_ROOT/source" "$WORKLOAD_ROOT/actions"

curl -fL \
  "https://huggingface.co/datasets/Contextbench/Tracebench/resolve/$TRACE_REPO_COMMIT/bench_artifacts/full/$TRACE_ARCHIVE?download=true" \
  -o "$WORKLOAD_ROOT/source/$TRACE_ARCHIVE"

printf '%s  %s\n' "$TRACE_SHA256" "$WORKLOAD_ROOT/source/$TRACE_ARCHIVE" \
  | sha256sum -c -
zstd -q -d -c "$WORKLOAD_ROOT/source/$TRACE_ARCHIVE" \
  | tar -xf - -C "$WORKLOAD_ROOT/source"

export TRACE_JSON="$WORKLOAD_ROOT/source/swe_raw/mini_swe_agent__poly/prettier__prettier-14400/prettier__prettier-14400.traj.json"
jq '{instance_id, trajectory_format, exit_status:.info.exit_status,
     mini_version:.info.mini_version, model_stats:.info.model_stats,
     environment:.info.config.environment}' "$TRACE_JSON"
```

这里同时固定 Hugging Face repo commit 和 archive SHA256。只固定下载 URL 不够，因为
数据集维护者可能替换 branch 上的文件。

下面从原 trajectory 生成 online-agent 使用的任务描述，并把 26 个 fenced bash action
提取成独立脚本。提取器不会执行任何 action：

```bash
python3 - "$TRACE_JSON" "$WORKLOAD_ROOT" <<'PY'
import hashlib
import json
import re
import sys
from pathlib import Path

trace_path = Path(sys.argv[1])
out = Path(sys.argv[2])
trace = json.loads(trace_path.read_text(encoding="utf-8"))

task_message = next(
    message["content"]
    for message in trace["messages"]
    if message["role"] == "user" and "<pr_description>" in message["content"]
)
task = task_message.split("<pr_description>", 1)[1].split("</pr_description>", 1)[0]
task = task.strip().removeprefix("Consider the following PR description:").strip()
task += """

Experiment constraints:
- Work only in /testbed and do not use web search.
- Do not install or update dependencies and do not run a full build.
- Run only a focused reproduction or focused test.
- Do not create a git commit. Finish with the root cause, changed files, and validation result.
"""
(out / "task.md").write_text(task, encoding="utf-8")

pattern = re.compile(r"```bash\s*\n(.*?)\n```", re.DOTALL)
actions = []
for message in trace["messages"]:
    if message["role"] == "assistant":
        actions.extend(pattern.findall(message.get("content", "")))
if len(actions) != 26:
    raise SystemExit(f"expected 26 actions, got {len(actions)}")

action_dir = out / "actions"
action_dir.mkdir(parents=True, exist_ok=True)
manifest = []
for index, command in enumerate(actions, 1):
    path = action_dir / f"{index:03d}.sh"
    payload = "#!/usr/bin/env bash\n" + command.rstrip() + "\n"
    path.write_text(payload, encoding="utf-8")
    manifest.append(
        f"{index:03d}\t{hashlib.sha256(payload.encode()).hexdigest()}\t"
        f"{command.splitlines()[0][:120]}"
    )
(out / "actions.tsv").write_text("\n".join(manifest) + "\n", encoding="utf-8")
print(f"wrote task.md and {len(actions)} actions")
PY

sed -n '1,40p' "$WORKLOAD_ROOT/actions.tsv"
```

`actions.tsv` 是本次 replay 的输入清单。执行前必须人工阅读 26 个脚本。开源
trajectory 本质上是不受信任的任意 shell；本文只允许在无其他数据、无 API key 的
一次性 microVM 中执行它。

## 4. 构造共同的 AgentENV 起点

原镜像已经包含任务 repo 和依赖，但默认 Node.js 是 16.20.2，不能运行当前 Claude
Code。固定的 Claude Code 2.1.236 在 npm metadata 中要求 Node.js `>=22.0.0`，
因此准备阶段安装单独的 Node.js 22.23.2 和固定版 Claude Code，然后创建
snapshot。
这个阶段不计入 workload 测量。

先从固定镜像冷启动：

```bash
PREP_ID="$(aenv start --cold "$WORKLOAD_IMAGE" \
  --detach --timeout 3600 --cpu 2 --memory 4096)"
printf 'PREP_ID=%s\n' "$PREP_ID"
aenv exec "$PREP_ID" bash -lc 'id; pwd; git -C /testbed status --short'
```

准备 Claude Code wrapper 和非 root agent 用户：

```bash
aenv exec "$PREP_ID" bash -lc '
set -euo pipefail
. /usr/local/nvm/nvm.sh
nvm install 22.23.2
nvm use 22.23.2
npm install -g @anthropic-ai/claude-code@2.1.236
claude_bin="$(readlink -f "$(command -v claude)")"
printf '\''#!/bin/sh\nexec "%s" "$@"\n'\'' "$claude_bin" \
  > /usr/local/bin/claude-agent
chmod 0755 /usr/local/bin/claude-agent
id agent >/dev/null 2>&1 || useradd -m -s /bin/bash -g 0 agent
chmod -R g+rwX /testbed
install -d -o agent -g 0 -m 0770 /workspace /workspace/artifacts
su -s /bin/bash agent -c '\''git config --global --add safe.directory /testbed'\''
git -C /testbed rev-parse HEAD > /workspace/original-head.txt
git -C /testbed add -A
git -C /testbed write-tree > /workspace/baseline-tree.txt
git -C /testbed reset --mixed
/usr/local/bin/claude-agent --version
'
```

`claude-agent` wrapper 直接指向 Node.js 22 全局 prefix 中安装的平台原生
Claude Code 二进制，但不改变 `/testbed` 默认 `PATH` 中的 Node.js 版本；
这样 agent 执行原项目 `node` 命令时仍使用镜像原有环境。
`baseline-tree.txt` 记录准备完成时的完整 Git tree，解决原镜像可能自带未提交 setup
文件的问题，后续 patch 都相对这个 tree 计算。

创建所有 online/replay 重复实验共享的只读起点：

```bash
aenv snapshot create "$PREP_ID" --name prettier-14400-base
aenv delete "$PREP_ID"
unset PREP_ID
```

此 snapshot 创建在 DeepSeek key 注入之前，可以安全地反复派生实验 sandbox。

## 5. 路径 A：DeepSeek online-agent

每次重复实验必须从 `prettier-14400-base` 新建 sandbox，不能在上一次的可写层上继续：

```bash
ONLINE_RUN="$(date -u +%Y%m%dT%H%M%SZ)-deepseek"
ONLINE_DIR="$WORKLOAD_ROOT/$ONLINE_RUN"
mkdir -p "$ONLINE_DIR"
ONLINE_ID="$(aenv start prettier-14400-base --detach --timeout 3600)"
printf '%s\n' "$ONLINE_ID" > "$ONLINE_DIR/sandbox-id.txt"
aenv upload "$ONLINE_ID" "$WORKLOAD_ROOT/task.md" /workspace/task.md
aenv upload "$ONLINE_ID" "$WORKLOAD_ROOT/actions/024.sh" /workspace/oracle.sh
aenv connect "$ONLINE_ID"
```

连接后首先进入非 root 用户；以下命令在 **sandbox 内** 执行：

```bash
su -s /bin/bash agent
cd /testbed
mkdir -p /workspace/artifacts/online
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
export DISABLE_AUTOUPDATER=1

start_ns="$(date +%s%N)"
set -o pipefail
/usr/local/bin/claude-agent -p \
  --output-format stream-json \
  --verbose \
  --permission-mode bypassPermissions \
  --tools 'Bash,Read,Edit,Write,Glob,Grep' \
  --max-turns 80 \
  "$(cat /workspace/task.md)" \
  2> /workspace/artifacts/online/claude.stderr.log \
  | tee /workspace/artifacts/online/trajectory.jsonl
claude_status=${PIPESTATUS[0]}
end_ns="$(date +%s%N)"

printf '%s\n' "$claude_status" > /workspace/artifacts/online/exit-code.txt
printf '%s\n' "$((end_ns - start_ns))" > /workspace/artifacts/online/duration-ns.txt
git add -A
git diff --binary --cached "$(cat /workspace/baseline-tree.txt)" \
  > /workspace/artifacts/online/patch.diff
git reset --mixed
git status --porcelain=v1 > /workspace/artifacts/online/git-status.txt
{
  date -u --iso-8601=seconds
  /usr/local/bin/claude-agent --version
  printf 'project_node='; node --version
  printf 'agent_node='; /usr/local/nvm/versions/node/v22.23.2/bin/node --version
  printf 'model=%s\n' "$ANTHROPIC_MODEL"
  printf 'image=%s\n' 'ghcr.io/timesler/swe-polybench.eval.x86_64.prettier__prettier-14400@sha256:e625c9b9776870e2cc87172e886bbc90cfc3d6ce1521492f113a46b3f6dfcf44'
  printf 'original_head=%s\n' "$(cat /workspace/original-head.txt)"
  printf 'baseline_tree=%s\n' "$(cat /workspace/baseline-tree.txt)"
} > /workspace/artifacts/online/environment.txt

unset ANTHROPIC_AUTH_TOKEN
exit "$claude_status"
```

`exit` 只退出 `agent` shell；再退出一次 root shell，回到 host。然后立刻下载产物：

```bash
# 测量窗口外运行固定的 task-specific oracle
aenv exec "$ONLINE_ID" bash -lc \
  'cd /testbed && bash /workspace/oracle.sh' \
  > "$ONLINE_DIR/oracle-output.txt"

aenv download "$ONLINE_ID" /workspace/artifacts/online "$ONLINE_DIR/"
test -s "$ONLINE_DIR/online/trajectory.jsonl"
tail -n 1 "$ONLINE_DIR/online/trajectory.jsonl" | jq .
```

在线运行允许 action 序列随模型变化。历史开源轨迹是选择该任务的依据，但不能据此
假设新的 DeepSeek trajectory 仍然文件访问占主导；每次运行都要重新统计 tool call、
syscall 和块层指标。

## 6. 路径 B：开源 action trace replay

Replay 不运行 Claude Code，也绝不能注入 DeepSeek key。仍从相同 snapshot 创建全新
sandbox：

```bash
REPLAY_RUN="$(date -u +%Y%m%dT%H%M%SZ)-replay"
REPLAY_DIR="$WORKLOAD_ROOT/$REPLAY_RUN"
mkdir -p "$REPLAY_DIR"
read -rsp 'AgentENV API key: ' AENV_API_KEY
printf '\n'
REPLAY_ID="$(
  curl -fsS -X POST \
    -H "X-API-Key: $AENV_API_KEY" \
    -H 'Content-Type: application/json' \
    -d '{"templateID":"prettier-14400-base","timeout":3600,"secure":true,"allow_internet_access":false}' \
    http://127.0.0.1:8000/sandboxes \
    | jq -er .sandboxID
)"
unset AENV_API_KEY
printf '%s\n' "$REPLAY_ID" > "$REPLAY_DIR/sandbox-id.txt"
for attempt in $(seq 1 30); do
  aenv exec "$REPLAY_ID" true && break
  sleep 1
done
aenv exec "$REPLAY_ID" true
aenv upload "$REPLAY_ID" "$WORKLOAD_ROOT/actions" /workspace/replay-actions
```

这里故意使用 HTTP API，因为当前 `aenv start` CLI 还没有网络策略参数。
warm-start 请求的字段名是 `allow_internet_access`（下划线）；它使 replay
sandbox 默认拒绝对外连接。AgentENV API key 只在 host shell 中短暂存在，
不会上传到 guest。

下面的 runner 每次都以 `/testbed` 为 cwd，和原 trajectory 的环境配置一致；每个
action 单独启动 shell，默认 60 秒 timeout，并分别保存 stdout、stderr、exit code 和
耗时：

```bash
aenv exec "$REPLAY_ID" bash -lc '
set -euo pipefail
out=/workspace/artifacts/replay
mkdir -p "$out/stdout" "$out/stderr"
printf "step\texit_code\tduration_ns\n" > "$out/steps.tsv"
for action in /workspace/replay-actions/*.sh; do
  step="$(basename "$action" .sh)"
  start_ns="$(date +%s%N)"
  set +e
  (cd /testbed && timeout --signal=TERM --kill-after=5s 60s bash "$action") \
    > "$out/stdout/$step.log" 2> "$out/stderr/$step.log"
  status=$?
  set -e
  end_ns="$(date +%s%N)"
  printf "%s\t%s\t%s\n" "$step" "$status" "$((end_ns - start_ns))" \
    >> "$out/steps.tsv"
done
git -C /testbed add -A
git -C /testbed diff --binary --cached "$(cat /workspace/baseline-tree.txt)" \
  > "$out/patch.diff"
git -C /testbed reset --mixed
git -C /testbed status --porcelain=v1 > "$out/git-status.txt"
cp /workspace/original-head.txt /workspace/baseline-tree.txt "$out/"
'

aenv download "$REPLAY_ID" /workspace/artifacts/replay "$REPLAY_DIR/"
column -t -s $'\t' "$REPLAY_DIR/replay/steps.tsv"
```

Replay 保留失败 action；不能使用 `set -e` 在第一个失败处终止，因为原 agent 可能正是
根据失败 observation 选择了下一步。另一方面，它不会把新产生的 observation 再反馈
给模型，后续 action 始终按已记录序列执行。

即使已禁止出站网络，也必须人工审计 26 个 action，不给 replay sandbox 任何
key，且只使用可抛弃的数据。网络隔离不会阻止恶意 shell 破坏 guest 内的文件。

## 7. 正确性检查与测量边界

将 agent/replay 的测量窗口限定为从第一个任务 action 开始到最后一个任务 action
结束。以下内容放在测量窗口之外：

- OCI pull/转换和 sandbox/template 创建；
- Node.js、Claude Code 或项目依赖安装；
- trajectory 下载、action 提取和 artifact 导出；
- 独立的正确性评测。

Tracebench artifact 自带的 `prettier__prettier-14400_result.json` 记录原轨迹
`resolved=true`，并列出相关 SVG embedded JavaScript format 测试通过。这个结果只证明
原轨迹，不证明本次 replay 或 DeepSeek 运行成功。

对新运行至少检查：

```bash
# online-agent 是否完整结束
test "$(cat "$ONLINE_DIR/online/exit-code.txt")" = 0
tail -n 1 "$ONLINE_DIR/online/trajectory.jsonl" | jq -e '.type == "result"'

# replay 是否完成全部 26 个 action；非零 action 保留在表中供分析
test "$(($(wc -l < "$REPLAY_DIR/replay/steps.tsv") - 1))" = 26
awk -F '\t' 'NR == 1 || $2 != 0' "$REPLAY_DIR/replay/steps.tsv"

# 两条路径都必须把 SVG <script> 内容当作 JavaScript 展开，而不是压成普通文本
grep -F '    document.addEventListener("DOMContentLoaded", () => {' \
  "$ONLINE_DIR/oracle-output.txt"
grep -F '      const node = document.getElementById("lastStroke");' \
  "$ONLINE_DIR/oracle-output.txt"
grep -F '    document.addEventListener("DOMContentLoaded", () => {' \
  "$REPLAY_DIR/replay/stdout/024.log"
grep -F '      const node = document.getElementById("lastStroke");' \
  "$REPLAY_DIR/replay/stdout/024.log"
```

上面的 oracle 直接复用原轨迹的第 24 个 reproduction，但对输出做了确定性断言：
JavaScript 语句必须被展开到独立缩进行。它比“命令返回 0”更强，且不需要全量测试。
完整正确性评测仍应在测量窗口外运行镜像内对应的 SVG embedded JavaScript
format test；Tracebench 原结果中的路径是
`tests/format/html/svg/embeded/jsfmt.spec.js->format`。测试命令应从固定镜像的现有
test runner 确认并写入实验元数据；不要让 agent 自己选择的测试结果充当唯一
oracle。同时检查最终 diff 只涉及预期的 `src/language-html`，并人工 review
`patch.diff`。

## 8. 如何比较文件系统方案

建议的最小实验矩阵是：

| 模式 | AgentENV block baseline | 待测 DAX/混合方案 | 主要用途 |
| --- | ---: | ---: | --- |
| DeepSeek online-agent | 至少 3 次 | 至少 3 次 | 端到端真实性；报告方差 |
| 固定 trace replay | 至少 5 次 | 至少 5 次 | 隔离文件系统差异 |

每次运行都从相同只读 snapshot 新建 sandbox，记录：

- snapshot/image/agent/model/prompt/action manifest 的 digest；
- 总耗时及逐 action 耗时；
- 读取/写入的 syscall 数与字节数；
- ublk 请求数、读取字节、平均/尾延迟；
- guest page cache、host cache 和冷/热状态；
- 最终 patch、exit code 和正确性结果。

不要在同一个 child 中连续跑 baseline 与新方案，也不要把 online-agent 的 API 等待时间
解释为文件系统耗时。Online 数据适合证明端到端影响；固定 replay 数据才适合把相同
action 序列送入不同存储实现。

若用 `strace` 做首次 workload 定性，可把第 6 节每个 action 的执行替换为：

```bash
strace -ff -qq -ttt -T -yy -s 256 \
  -e trace=%file,%desc,%process \
  -o "$out/strace/$step" \
  bash "$action"
```

需要预先创建 `$out/strace`。开启 `strace` 的结果不得用于报告正式性能数据。

## 9. 清理

确认两条路径的 artifact 已下载后，删除一次性 sandbox：

```bash
test -s "$ONLINE_DIR/online/trajectory.jsonl"
test -s "$REPLAY_DIR/replay/steps.tsv"
aenv delete "$ONLINE_ID"
aenv delete "$REPLAY_ID"
unset ONLINE_ID REPLAY_ID
```

需要继续重复实验时保留 `prettier-14400-base`。整个 workload 结束后再删除 snapshot：

```bash
aenv template delete prettier-14400-base
```

本地 `$WORKLOAD_ROOT` 包含 prompt、原轨迹、可执行 action、输出和 patch，应按实验数据
管理；确认归档前不要删除。它不应包含 DeepSeek API key。

## 10. 已知限制

- Open trace 由 mini-SWE-agent/GPT-5 产生，online 路径是 Claude Code/DeepSeek；它们的
  工具集合和 agent policy 不同。这里只复用任务与 action 序列，不声称复现原模型。
- Replay 是 **action-level replay**，不是 observation-conditioned replay。文件状态或
  工具版本改变时，某一步输出可能不同，但后续仍执行固定 action。
- 共同 snapshot 比历史镜像多了 Claude Code、Node 22 wrapper 和 agent 用户，因此不
  是对 2025/2026 原运行的 bit-for-bit 重建；它的意义是让本项目的两个路径共享起点。
- action 比例不是 I/O 时间比例；是否真正触发 ublk 取决于 guest page cache 与访问
  状态。这个问题正是后续 block/DAX 实验需要测量的对象。
- `git diff`、`rg`、Node 模块加载本身也会访问 `.git`、源码和 `node_modules`；分析时
  不应只统计 Claude Code 的显式 `Read` 工具。
- 这个实例只覆盖 `moti.md` 中的“文件读写主导”第一阶段，不能代表多分支
  fork 或包含依赖安装、全量构建和测试的复杂任务。

## 11. 参考资料

- 仓库内 [AgentENV sandbox 与网络策略](../../baselines/AgentENV/docs/src/concepts/sandboxes.md)
- [Claude Code CLI reference](https://code.claude.com/docs/en/cli-usage)
- [Claude Code 2.1.236 npm package](https://www.npmjs.com/package/@anthropic-ai/claude-code/v/2.1.236)
- [DeepSeek × Claude Code](https://api-docs.deepseek.com/quick_start/agent_integrations/claude_code/)
- [Contextbench/Tracebench](https://huggingface.co/datasets/Contextbench/Tracebench)
- [Prettier #14400](https://github.com/prettier/prettier/pull/14400)
