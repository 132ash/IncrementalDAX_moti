# Prettier #14400：TrEnv-X 与 AgentENV 对比

最新 TrEnv-X 运行：`20260914T124731Z-trenvx-ch-dax-replay`；对照 AgentENV 运行：`20260914T124833Z-agentenv-replay`。

## 核心结果

| runtime | create API (ms) | 26 actions total (ms) | action p50 (ms) | action p95 (ms) | guest peak (MiB) | runtime cgroup peak (MiB) | VMM peak RSS (MiB) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| AgentENV cold/FC + OverlayBD direct I/O | 2573.4 | 2414.5 | 11.8 | 145.4 | 400.8 | 597.7 | 495.2 |
| TrEnv-X restore/custom CH + pmem/DAX | 1360.5 | 1376.2 | 10.0 | 83.2 | 317.0 | 242.5 | 635.0 |

TrEnv-X 本轮正确性和 pmem/DAX 验收：**通过**；两侧 action manifest digest 一致：**是**。两行 host cgroup 口径不同：TrEnv-X 是单 sandbox cgroup，AgentENV 是整个 server 容器 cgroup；因此可直接比较 action/guest 数据，host cgroup 数值只作诊断，不能解释为严格的逐 sandbox 差值。

在这一轮中，TrEnv-X 的 create API、26-action 总时间和 guest peak 分别低 **47.1%**、**43.0%** 和 **20.9%**。第一列实际比较 AgentENV OCI cold start 与 TrEnv-X snapshot restore，并非同类 restore；整张表也是单次端到端管线结果，差异同时包含 VMM、rootfs、snapshot 和 I/O 路径，不能单独归因于 DAX。

Guest page cache、匿名页、kernel/other 分桶，以及启动和 action 差异的证据分析见 [`analysis.md`](analysis.md)。

## 逐 action 延迟

| action | tool | duration (ms) | exit |
| ---: | --- | ---: | ---: |
| 001 | `ls` | 13.378 | 0 |
| 002 | `ls` | 5.015 | 0 |
| 003 | `ls` | 8.511 | 0 |
| 004 | `nl` | 7.634 | 0 |
| 005 | `nl` | 11.578 | 0 |
| 006 | `nl` | 13.468 | 0 |
| 007 | `nl` | 10.003 | 0 |
| 008 | `rg` | 7.555 | 127 |
| 009 | `grep` | 8.763 | 0 |
| 010 | `nl` | 10.545 | 0 |
| 011 | `nl` | 7.933 | 0 |
| 012 | `nl` | 8.750 | 0 |
| 013 | `nl` | 9.326 | 0 |
| 014 | `nl` | 5.193 | 0 |
| 015 | `nl` | 12.299 | 0 |
| 016 | `applypatch` | 3.474 | 127 |
| 017 | `sed` | 4.510 | 0 |
| 018 | `sed` | 8.824 | 0 |
| 019 | `nl` | 10.045 | 0 |
| 020 | `git` | 23.629 | 0 |
| 021 | `git` | 29.164 | 0 |
| 022 | `perl` | 15.268 | 0 |
| 023 | `node` | 500.110 | 0 |
| 024 | `node` | 517.302 | 0 |
| 025 | `echo` | 83.198 | 0 |
| 026 | `echo` | 40.709 | 0 |

## 复现信息

原始数据、stdout/stderr、patch、guest 内存/vmstat、host per-sandbox cgroup 采样、VMM RSS/PSS、内核命令行和 mount 拓扑位于 [`raw/20260914T124731Z-trenvx-ch-dax-replay/`](raw/20260914T124731Z-trenvx-ch-dax-replay/)。这是一轮管线验证；性能结论应至少做 10 次交错重复并报告方差。
