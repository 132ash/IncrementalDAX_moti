# Prettier #6604：四轮固定输入

候选来自固定 Tracebench revision `7da2e4f45b330be8b6e8f1cff835247723cb3341`：

- 轨迹： `openhands-OpenAI__GPT-5-prettier__prettier-6604-f6c47d03`
- 归档 SHA256： `8481e777e318e7e4c7cd15ed8a240295af2d07a38e1c86f4a242e8c025f2cd30`
- 原记录路径： `swe_raw/openhands__poly/prettier__prettier-6604`
- Tracebench 标记： `solved=true`, 65 steps
- 镜像： `ghcr.io/timesler/swe-polybench.eval.x86_64.prettier__prettier-6604@sha256:8159d38fcbd6d5f09402d93d3e15cf2a891058ddd835a224f1d6b3357a87cc94`

原轨迹围绕 TypeScript 括号打印问题，主要操作是目录/源码/测试检索与分段读取，同时
多次启动 Jest 和 Prettier。这里没有逐字重放 OpenHands 专用的 editor tool，而是保留
同一访问路径并整理成 4 轮、每轮 8 个可审计 shell action。共 32 个 action，其中 9 个
显式启动 Node/Jest/Prettier（含 5 次格式化和 2 次实际 Jest 执行）；不同轮的主访问文件
集合不同，且修改会跨 checkpoint 保留。

## 32 个 action 的具体含义

每个 action 是一次独立、计时的 shell 调用。`sed` 负责按行读取，`grep` 做内容检索，
`find` 枚举文件，`sort` 固定输出顺序；末尾的 `sed -n` 只限制输出量，不减少前面命令
已经完成的目录遍历或检索。

### 第 1 轮：仓库与打印器入口发现

| 步骤 | 工具 | 操作与目的 |
| --- | --- | --- |
| 001 | find/sort/sed | 枚举仓库两层内的文件，建立项目结构概览。 |
| 002 | sed | 读取 `package.json` 前 180 行，确认脚本、依赖和版本。 |
| 003 | find/sort | 枚举 `src/language-js` 顶层文件，定位 JS/TS printer。 |
| 004 | grep/sed | 在 language-js 中搜索 parenthesized/conditional type 相关实现。 |
| 005 | sed | 读取 `needs-parens.js` 前 240 行，检查通用括号判定。 |
| 006 | sed | 读取 `printer-estree.js` 3360–3500 行的类型打印逻辑。 |
| 007 | Node/Prettier | 启动项目自己的 CLI 并输出版本，验证运行入口。 |
| 008 | Node/Jest | 构建 Jest 测试索引并列出匹配 TypeScript 的测试，不执行测试。 |

### 第 2 轮：定位 indexed-access 问题并构造复现

| 步骤 | 工具 | 操作与目的 |
| --- | --- | --- |
| 001 | grep/sed | 搜索 `TSIndexedAccessType` 的实现位置。 |
| 002 | sed | 读取 printer 中 3120–3275 行，查看 indexed-access case 上下文。 |
| 003 | grep/sort/sed | 遍历 tests，找出含 `keyof` 或 indexed-access 的文件。 |
| 004 | find/sort/sed | 枚举 TypeScript 测试文件，建立候选回归测试集合。 |
| 005 | sed | 读取 printer 前部 100–210 行，查看辅助函数和调度结构。 |
| 006 | grep | 定位 `pathNeedsParens` 和 `linesWithoutParens` 的调用点。 |
| 007 | printf + Node/Prettier | 写入 union/keyof indexed-access 临时文件并实际格式化。 |
| 008 | printf + Node/Prettier | 通过 stdin 格式化 conditional type 的两个括号边界案例。 |

### 第 3 轮：修改实现并做聚焦验证

| 步骤 | 工具 | 操作与目的 |
| --- | --- | --- |
| 001 | sed | 读取 printer 2720–2860 行，检查相邻 type node cases。 |
| 002 | grep/sed | 搜索 union、intersection 和 type-operator 的处理路径。 |
| 003 | Python/Pathlib | 精确替换 `TSIndexedAccessType` case：解包显式括号并为四类 object type 补括号。 |
| 004 | git diff | 展示刚修改的 printer patch。 |
| 005 | sed | 重新读取修改位置附近 3180–3255 行。 |
| 006 | grep/sed | 搜索现有 `T1`–`T4` 类型测试案例。 |
| 007 | printf + Node/Prettier | 写入新的 union/keyof 临时案例并用已修改 printer 格式化。 |
| 008 | Node/Jest | 实际执行 `tests/typescript_keyof/jsfmt.spec.js` 并校验 snapshot。 |

### 第 4 轮：边界案例、integration test 与最终检查

| 步骤 | 工具 | 操作与目的 |
| --- | --- | --- |
| 001 | find/sort/sed | 枚举 test harness 与 integration test 文件。 |
| 002 | grep/sed | 在 test config、integration tests 和 scripts 中搜索 TypeScript 接入点。 |
| 003 | sed | 读取 `tests_config/run_spec.js`，检查格式化测试 harness。 |
| 004 | printf + Node/Prettier | 写入 intersection/conditional indexed-access 案例并格式化；输出也是跨轮 oracle。 |
| 005 | printf + Node/Prettier | 从 stdin 格式化泛型与 readonly array 中的 indexed-access 案例。 |
| 006 | Node/Jest | 实际执行 parser API integration suite（6 tests）。 |
| 007 | git | 执行 whitespace/error 检查并列出工作树修改。 |
| 008 | git/sed | 输出最终 diff stat 和 printer 的完整受限 diff。 |

状态变化只有 round 2/007、round 3/007、round 4/004 写入 `/tmp`，以及 round 3/003
修改仓库源码；后者与 `/tmp` 文件都会随 sandbox snapshot 进入下一轮。其他 action 均为
只读访问或将结果写到 runner 的 stdout/stderr artifact。
