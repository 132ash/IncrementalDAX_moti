# 执行实验与验收

先完成 [AgentENV](agentenv-baseline.md) 和 [TrEnv-X](trenvx-baseline.md) 部署。以下命令从仓库根目录运行；两套系统顺序测量，使用相同固定镜像和动作。TrEnv-X 的 setup 与 run 均要求 `conda activate hybridfs`。

## Exp1：单任务回放

```bash
bash motivation/experiments/run.sh agentenv prettier-14400
conda activate hybridfs
bash motivation/experiments/run.sh trenvx prettier-14400 setup
bash motivation/experiments/run.sh trenvx prettier-14400
```

每侧执行 26 个动作，默认先清 guest cache。结果位于 `motivation/results/exp1-single-app-smoke/{agentenv,trenvx}/`；TrEnv-X 分析器读取 AgentENV 结果生成比较。动作超时默认 60 s，guest 内存采样目标间隔 20 ms。AgentENV 可通过环境变量 `DROP_GUEST_CACHES=0` 保留启动后缓存；TrEnv-X 的该值在 `config.env` 中直接赋值，需修改配置才生效。变体必须单独标注。

## Exp2：四轮保存与恢复

```bash
bash motivation/experiments/run.sh agentenv-page-cache prettier-6604
bash motivation/experiments/run.sh agentenv-drop-cache prettier-6604
conda activate hybridfs
bash motivation/experiments/run.sh trenvx prettier-6604 setup
bash motivation/experiments/run.sh trenvx prettier-6604
python3 motivation/experiments/exp2-multi-rounds/compare.py
```

三组结果分别位于 `motivation/results/exp2-multi-rounds/{agentenv-preserve-cache,agentenv-drop-cache,trenvx}/`。每轮 8 个动作，默认动作超时 300 s、guest 采样间隔 20 ms。第四轮也做 checkpoint/restore；`transitions.tsv` 记录生命周期耗时，比较只计工具动作。

## Exp3：多任务多分支

Exp3 使用当前目录的私有入口。公共 `run.sh` 的 RL 路由仍指向旧 Exp5，不能使用。先选任务；从 `task.json` 读取固定镜像，避免手工复制错误 digest：

```bash
export EXP="$PWD/motivation/experiments/exp3-RL-fork"
export TASK=xarray-6992
# TASK 也可为 prettier-6604 或 sphinx-7590
export WORKLOAD_NAME="$TASK-rl-fork"
export WORKLOAD_IMAGE="$(python3 -c 'import json,os; from pathlib import Path; print(json.loads((Path(os.environ["EXP"])/"workloads"/os.environ["WORKLOAD_NAME"]/"task.json").read_text())["source_image"])')"
export DERIVED_IMAGE="mixfs/$TASK-exp3-trenvx:frozen"
export TEMPLATE_ID="$TASK-exp3-ch-layered"
export RESULT_ROOT="$PWD/motivation/results/exp3-RL-fork/$TASK"
python3 "$EXP/workloads/$WORKLOAD_NAME/plan.py"

bash "$EXP/systems/agentenv/set-balloon.sh" off
conda activate hybridfs
bash "$EXP/systems/trenvx/setup.sh"
```

每个任务独立 setup 一次；已有模板且输入未变时跳过。三个任务共享默认 Btrfs data root，但模板名不同。然后运行所需调度（可只保留循环中的一个场景）：

```bash
for scenario in grpo bpo tvcache; do
  BALLOON_MODE=off \
    OUTPUT_ROOT="$RESULT_ROOT/agentenv-balloon-off/$scenario" \
    bash "$EXP/systems/agentenv/run.sh" "$scenario"
  OUTPUT_ROOT="$RESULT_ROOT/trenvx/$scenario" \
    bash "$EXP/systems/trenvx/run.sh" "$scenario"
  python3 "$EXP/compare.py" "$WORKLOAD_NAME" "$scenario" "$RESULT_ROOT"
done
```

显式 `OUTPUT_ROOT` 必不可少：runner 默认仍写旧 `exp5-RL-fork`。循环中每侧都完成清理后才运行另一侧。每个场景最终保留七个实例，完成终态采样再清理。`run.sh` 自动调用分析器并更新 `latest-run.txt`；`compare.py` 读取两个组各自的 latest run，输出 BPO 的 `summary.md`、另外两组的 `grpo-summary.md/tvcache-summary.md` 和逐点差额 TSV。

Exp3 controller 当前实际将动作超时设为 **600 s**、guest 采样间隔设为 **0.1 s**；host VMM 监测目标间隔也是 0.1 s。不要把 `config.env` 的 300 s/0.05 s 直接写作本次运行的生效值。物理文件页在每个 segment 后和终态采样，终态默认额外保留 3 s。

## 验收与结果口径

| 实验 | 完整性与正确性检查 |
| --- | --- |
| Exp1 | `steps.tsv` 有 26 步；第 24 步 SVG script 输出满足缩进 oracle；检查最终 patch。保留原轨迹中 `rg/applypatch` 缺失的失败动作 |
| Exp2 | 四轮各 8 步；四次 transition；第 4 轮 004 的输出含 `type G = (A & B)[keyof C];`，结合 Jest 与最终 patch 检查状态继承 |
| Exp3 | GRPO/BPO/TVCache 的物理 segment 数正确，采样点数 = segment 数 + 1；终态 7 VM；除 GRPO 外派生 child 总数为 6；输入哈希、动作数与七条终态 patch 在两系统间一致 |

Exp3 比较器还审计失败集合：保留 agent 的失败探索，允许其代码中列出的只读发现命令 exit 1/141 差异。它证明成对回放一致性，**不证明通过 SWE-bench 隐藏测试或每个候选修复都正确**。模型选择的聚焦测试和独立任务评测应区分。

时间与内存分别解释：

- **工具时间**：guest 内每条 shell 动作的 wall time；不含 API 请求、sandbox 创建、上传下载、checkpoint/模板构建和测量。聚合工具时间也不是并发任务的端到端完成时间；Exp3 当前表中仅作审计。
- **文件内容物理量**：guest file-LRU 页经 KVM slot 与 host pagemap 映射到 host PFN，跨 VM 去重，再加基础/历史 DAX 层映射 PSS。它不包含全部匿名内存、daemon、kernel 或未映射 host block cache。
- **VMM PSS**：与文件内容物理量有交集，不能相加。当前 Exp3 主比较只列 AgentENV 的 VMM PSS 观测峰值，TrEnv-X 留空。
- **采样差额**：按相同 segment 完成里程碑配对；并发分支当时的进度可能不同。离散采样会漏掉段内峰值，差额是条件优化空间估计，不是逐页因果归因。当前成对结果每组一次，不能估计方差。

## 原始记录与离线分析

保留 raw 下的元数据、输入哈希、stdout/stderr、退出码、patch、生命周期事件和 `host/` 采样。Exp3 重点文件为 `metadata.json`、`events.tsv`、`segments.tsv`、`metrics.json`、`host/physical-samples/*/physical-memory.json` 与 `host/memory-samples.tsv`。

本 checkout 只保留报告与派生产物，`**/raw/` 被 Git 忽略且当前不存在。以下复算命令要求先补齐对应 raw；`latest-run.txt` 只记录 ID，不包含运行数据。没有原始数据时仍可运行 workload 的 `plan.py`，但无法复核报告中的实际测量值。

```bash
# 将 RAW_DIR 设置为某次已有运行目录
python3 motivation/experiments/exp3-RL-fork/analyze.py "$RAW_DIR"
python3 motivation/experiments/exp3-RL-fork/compare.py \
  xarray-6992-rl-fork bpo motivation/results/exp3-RL-fork/xarray-6992
```

分析会重写派生报告。强制终止后先根据 raw 记录核对残留实例/模板，归档数据后再清理；不要把删除阶段的内存变化算作 workload 收益。
