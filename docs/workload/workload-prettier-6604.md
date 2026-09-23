# Prettier #6604：TypeScript 括号语义修复

任务围绕 TypeScript 类型的重复括号与 indexed-access 打印，例如括号中的 union、conditional type 或 `keyof` 作为 `T[K]` 的 object 时，要避免冗余括号，同时保留必要的分组语义。

镜像含 Prettier 1.18.2；Exp3 的 `task.json` 固定基线 commit 为 `affa24ce764bd14ac087abeef0603012f5c635d6`。Exp2/3 使用同一镜像：

```text
ghcr.io/timesler/swe-polybench.eval.x86_64.prettier__prettier-6604@sha256:8159d38fcbd6d5f09402d93d3e15cf2a891058ddd835a224f1d6b3357a87cc94
```

## Exp2：四轮人工整理轨迹

参考 Tracebench revision `7da2e4f45b330be8b6e8f1cff835247723cb3341` 的 `openhands-OpenAI__GPT-5-prettier__prettier-6604-f6c47d03`，原记录为 `solved=true`、65 steps，archive SHA256 为 `8481e777e318e7e4c7cd15ed8a240295af2d07a38e1c86f4a242e8c025f2cd30`。

实验将原 OpenHands editor/tool 操作整理为 **4 轮 × 8 个 shell 动作**，不是原始 65 步的逐字重放：

| 轮次 | 主要工作 | 状态变化与验证 |
| --- | --- | --- |
| 1 | 发现仓库、printer、括号判定入口 | Node 版本与 Jest 测试索引 |
| 2 | 定位 `TSIndexedAccessType`，查源码与测试 | 在 `/tmp` 写复现，格式化 union/keyof/conditional 案例 |
| 3 | 修改 `printer-estree.js` 的 indexed-access 处理 | 检查 diff，执行 `typescript_keyof` Jest |
| 4 | 读取 harness，验证更多边界 | parser API integration suite（6 tests）、diff 与 oracle |

共 9 个动作显式启动 Node/Jest/Prettier，其中 5 次格式化、2 次实际 Jest 测试。每轮后保存并恢复，源码修改及 `/tmp` 复现文件须继承。oracle 是第 4 轮 004 的 `type G = (A & B)[keyof C];`。完整逐动作表保留在[输入 README](../../motivation/experiments/exp2-multi-rounds/workloads/prettier-6604/README.md)。

## Exp3：七条模型采样轨迹

[输入目录](../../motivation/experiments/exp3-RL-fork/workloads/prettier-6604-rl-fork/README.md)包含 DeepSeek 采样的主干和六条延续分支。

采样元数据记录的实际容器镜像名是本地派生标签 `mixfs/prettier-6604:exp2`（采样时间 `20260918T155905Z`），而非 digest；当前回放的来源 digest 由 `task.json` 固定为上文镜像。若重新采样，还需核验该本地派生镜像的构建来源，不能把标签当作不可变版本证明。

- 主干：`read_repo → read_typescript → core_patch → core_verify → backbone_finish`。
- early 三分支从调查后状态出发，分别探索 union、conditional、keyof。
- late 三分支从候选修复验证后状态出发，补充上述语义边界。
- early/late 各自共享一个额外 inspect segment，因此 TVCache 能进一步复用前缀。

GRPO/BPO/TVCache 分别执行 35/17/13 个物理 segment；现有 BPO 报告为 84 个工具动作。使用源码读取、最小复现、编辑和聚焦 Jest，失败命令仍属于轨迹。遗留 `edit.py` 或未引用的 segment 不定义当前输入，以 `rollouts.json` 和 manifest 为准。

两个实验的任务相同，但输入与 checkpoint 协议不同。Exp3 的两个系统须逐路径得到相同终态 patch；这不能替代独立的任务正确性评测。结果见 [Prettier BPO](../../motivation/results/exp3-RL-fork/prettier-6604/summary.md)，其余调度见[结果索引](../../motivation/results/README.md)。
