# TrEnv-X 部署

实验使用定制 Cloud Hypervisor，而非 TrEnv-X 的 Firecracker 路径。固定版本：Cloud Hypervisor commit `9e0056eb750096f3bf8ed491c345ef9241fd527e`，Rust `1.85`，guest kernel `6.1.134`，配置名 `ch-6.1.134`。Exp1 setup 明确要求 Go `1.23.*`；过新的 Rust 生成的 syscall 可能与该 VMM 的 seccomp allow-list 不兼容。

## Host 工具与权限

先安装 Docker、Go 1.23、rustup，以及 `make/gcc/bc/bison/flex/acl/libcap2-bin/e2fsprogs` 等构建工具。建立脚本要求的 Python 环境：

```bash
conda create -n hybridfs python=3.12 -y
conda activate hybridfs
rustup toolchain install 1.85
go version
sudo -n true
```

若尚未安装 `cgexec`，使用 TrEnv-X 安装脚本所引用的实现：

```bash
git clone https://github.com/huang-jl/cgexec.git /tmp/incrementaldax-cgexec
make -C /tmp/incrementaldax-cgexec build
sudo make -C /tmp/incrementaldax-cgexec install
command -v cgexec
```

记录该工具实际 commit。TrEnv-X 的历史 gitlink 可能使通用递归初始化失败，不应依赖它自动提供可执行文件。

准备 KVM 用户组、网络 namespace、host 名称解析、数据目录和 Exp1 cgroup：

```bash
sudo usermod -aG kvm "$USER"
# 新加入用户组后重新登录，再确认 /dev/kvm 可读写
sudo mkdir -p /run/netns /var/lib/trenvx
sudo setfacl -m "u:$USER:rwx" /run/netns
sudo setfacl -m "u:$USER:rw" /etc/hosts
sudo chown "$USER:$(id -gn)" /var/lib/trenvx
sudo mkdir -p /sys/fs/cgroup/user.slice/trenvx
sudo chown "$USER" /sys/fs/cgroup/user.slice/trenvx \
  /sys/fs/cgroup/user.slice/trenvx/cgroup.procs \
  /sys/fs/cgroup/user.slice/trenvx/cgroup.subtree_control
for controller in $(cat /sys/fs/cgroup/user.slice/trenvx/cgroup.controllers); do
  printf '+%s\n' "$controller" > /sys/fs/cgroup/user.slice/trenvx/cgroup.subtree_control
done
```

构建 Makefile 给 orchestrator、template-manager 和 bind-mount helper 配置 capabilities；各实验 setup 另为 `/run/xtables.lock` 配置 ACL。Exp2/3 setup 会创建自己的 cgroup。需要支持 reflink 的 XFS/Btrfs 数据目录来避免普通模板复制退化；Exp3 则强制使用下述 Btrfs 卷。

## 修正机器路径，构建模板

三个实验的 `systems/trenvx/config.toml` 中，`envd_path` 仍指向原实验机 `/home/shao/MixFS/...`。在新的 Linux checkout 中改成当前仓库绝对路径：

```bash
for exp in exp1-single-app-smoke exp2-multi-rounds exp3-RL-fork; do
  sed -i "s|^envd_path = .*|envd_path = \"$PWD/baselines/TrEnv-X/packages/envd/bin/envd\"|" \
    "motivation/experiments/$exp/systems/trenvx/config.toml"
done
bash motivation/experiments/run.sh trenvx prettier-14400 setup
bash motivation/experiments/run.sh trenvx prettier-14400
```

setup 依次构建包含 workload 的派生 Docker 镜像、指定 VMM、`envd/orchestrator/cli/template-manager`，必要时编译 CH guest kernel，安装本地 Python SDK，并生成 snapshot 模板。Exp1 还写入 `provenance.env`（commit、kernel/rootfs 哈希）。run 启动本地 orchestrator，经 SDK 创建 sandbox，检查 pmem/DAX，采集后删除实例。

已有模板时 setup 默认失败，避免覆盖；`REBUILD_TEMPLATE=1` 会删除并重建该模板。修改动作、镜像或 overlay-init 后须有意重建，不在旧模板上混跑。

## 三个实验的运行布局

| 实验 | data root | orchestrator / cgroup | 基础模板 |
| --- | --- | --- | --- |
| Exp1 | `/var/lib/trenvx` | `15000` / `user.slice/trenvx` | `prettier-14400-ch-dax` |
| Exp2 | `/var/lib/trenvx` | `15001` / `user.slice/trenvx-exp2` | `prettier-6604-exp2-ch-dax` |
| Exp3 | `/var/lib/trenvx-exp5-cow` | `15005` / `user.slice/trenvx-exp5` | 每个任务独立设置 `TEMPLATE_ID` |

Exp3 setup 调用 `prepare-cow-volume.sh`：首次创建 **100 GiB 稀疏文件** `/var/lib/trenvx-exp5-cow.img`，格式化 Btrfs，使用 loop direct I/O 挂载到 data root，选项为 `noatime,compress=no`。这不是立即占满 100 GiB，但实际磁盘空间需容纳逐步写入的数据。重跑复用该卷；实验清理不删除基础模板、数据卷和缓存。

Exp3 的 `kernels` 默认链接到 `/var/lib/trenvx/kernels`。先完成 Exp1 setup 可准备共同 kernel；从 Exp3 独立部署时也要先创建该目标目录。Exp3 运行前要求 Btrfs 已挂载且无其他 Cloud Hypervisor VM。

`DATA_ROOT`、端口和 cgroup 同时出现在 env、TOML 与 runner 中；尤其 `start-backend.sh` 直接读取静态 TOML。不要只覆盖环境变量就认为完成了迁移。文档命令保留默认 host 布局，只改变支持动态生成的任务镜像和模板。

## 检查与排错

- guest 检查 `/proc/mounts`、`/dev/pmem*` 和 `dax=always`；Exp3 还检查 checkpoint 层和 `checkpoint-layers.json`。
- `sudo -n bpftrace -l 'tracepoint:syscalls:sys_enter_ioctl'` 应能找到 Exp3 所需 tracepoint；PFN 不可读时物理归因会失败，不能回退成 guest `Cached` 冒充物理内存。
- 端口检查失败查看 raw 下 `orchestrator.stderr.log`；模板构建失败查看 `checkpoint-*-template-manager.log`；PSS/物理采样失败查看 `host/` 日志。
- 私有 SDK 适配直连 guest IP 的 envd（默认端口 49982），不依赖生产代理域名。
