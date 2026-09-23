# Prettier #14400：SVG 中的 script 格式化

用于 [Exp1](../../motivation/experiments/exp1-single-app-smoke/README.md)。任务要求修复 HTML parser 对 SVG `<script>` 内嵌 JavaScript 的处理；源码改动小，调查阶段大量访问仓库文件，适合首先验证 block/DAX 的执行与测量链路。

## 固定来源

| 项目 | 固定值 |
| --- | --- |
| 实例 | `prettier__prettier-14400` |
| 数据源 | Contextbench/Tracebench，revision `7da2e4f45b330be8b6e8f1cff835247723cb3341` |
| trajectory | `miniswe-OpenAI__GPT-5-prettier__prettier-14400-477c8cff` |
| 原 agent / 模型 | mini-SWE-agent 1.17.3 / GPT-5 |
| archive SHA256 | `205c04ee98c69b1d9a6a9ef9639ff9d5ce5ae7fa36675f2404e2c4660fba8528` |
| 原记录 | `solved=true`、`exit_status=Submitted`；只代表原轨迹 |

镜像固定为：

```text
ghcr.io/timesler/swe-polybench.eval.x86_64.prettier__prettier-14400@sha256:e625c9b9776870e2cc87172e886bbc90cfc3d6ce1521492f113a46b3f6dfcf44
```

当前输入在 [workloads/prettier-14400](../../motivation/experiments/exp1-single-app-smoke/workloads/prettier-14400/README.md)：26 个 `actions/*.sh` 和 `actions.tsv`，保留原命令顺序。每个 action 在 `/testbed` 中单独启动 shell。

## 动作与验证

| 步骤 | 数量 | 内容 |
| --- | ---: | --- |
| 1–15 | 15 | 导航、检索、读取 parser 源码 |
| 16–22 | 7 | 修改、撤回失败尝试、检查源码 |
| 23–24 | 2 | Node 最小复现，验证 SVG 内 JavaScript 格式化 |
| 25–26 | 2 | 暂存修改并输出 diff |

原轨迹中 `rg` 和 `applypatch` 不可用的动作仍保留，属于预期探索失败。runner 继续执行后续步骤并记录退出码。oracle 检查第 24 步输出中的 `document.addEventListener(...)` 与 `const node = ...` 是否展开为独立缩进行，并检查最终 patch；不能只检查 shell 返回 0。

24/26 个动作直接围绕文件，但这不是文件 I/O 耗时占比；真正的块读取还受 guest cache 影响。该任务不包含依赖安装、全量构建和多分支 fork。

## 运行与在线路径

自动 replay 直接使用固定镜像，AgentENV 冷启动后上传动作；TrEnv-X 将同一输入烘焙到模板。命令与结果见 [Exp1 README](../../motivation/experiments/exp1-single-app-smoke/README.md)。

早期另有 Claude Code/DeepSeek online-agent 方案：在共同 snapshot 中准备 Node 22、Claude Code 和 agent 用户，再采集新的轨迹。它与当前自动 replay 的准备状态不同，不能混用性能数字。完整下载、提取、在线执行与原始轨迹审计步骤保存在[历史操作手册](../deployment/prettier-14400-online.md)。
