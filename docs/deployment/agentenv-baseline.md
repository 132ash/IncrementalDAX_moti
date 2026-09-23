# AgentENV 部署

当前实验复用名为 `aenv-server` 的单节点 Docker 服务。host 采集器和 balloon 切换脚本都依赖这一名称；不能只启动 systemd 服务后原样运行这些脚本。

## 构建并启动

从本仓库子模块构建，以包含 `free_page_reporting` 修改；上游浮动 `latest` 不能保证含该补丁。以下用于尚无同名服务的新实验机：

```bash
sudo bash baselines/AgentENV/scripts/docker-setup.sh
docker build -f baselines/AgentENV/deploy/docker/Dockerfile.agentenv \
  -t incrementaldax/agentenv:6c67f92 baselines/AgentENV
docker run -d --name aenv-server \
  --privileged --device /dev/kvm -v /dev:/dev \
  -p 127.0.0.1:8000:8000 \
  incrementaldax/agentenv:6c67f92
curl -fsS http://127.0.0.1:8000/health

bash baselines/AgentENV/scripts/install-cli.sh
docker exec aenv-server cat /workspace/env/secrets/api-key
aenv auth
# 按提示填写 http://127.0.0.1:8000 和上一条命令显示的 key
aenv --version
aenv list
```

`docker-setup.sh` 会在 host 准备 ublk 和 sysctl；首次构建/启动还会下载运行依赖。已有服务时先核对版本，不重复创建容器。配置在 `/workspace/config/default.toml`，镜像缓存与 snapshot 等数据位于 `/workspace/env`。上述最小部署依赖容器可写层，删除容器会删除其中状态；普通重启会保留。

`install-cli.sh` 是上游下载入口，需记录实际 `aenv --version`。同时记录 server 的 Git commit、Docker image ID 和实际 Firecracker/kernel 版本；server 源码固定不等于所有下载资产都已固定。构建细节见[子模块 Docker 文档](../../baselines/AgentENV/docs/src/deployment/docker.md)。

## 冒烟与缓存策略

```bash
test "$(aenv list | jq 'length')" = 0
sudo -n true
bash motivation/experiments/run.sh agentenv prettier-14400
```

runner 冷启动固定 workload 镜像，上传动作与 guest runner，默认清 guest cache，再测量并下载产物。Exp1 不要求预建 Claude Code snapshot。结果写入 `motivation/results/exp1-single-app-smoke/agentenv/`，结束或常规异常时删除实例；`KEEP_SANDBOX=1` 只用于调试。

Exp2 的 `agentenv-page-cache` / `agentenv-drop-cache` 选择 checkpoint 前缓存策略；该选择不改变 balloon 设备。Exp3 主比较使用自然缓存且关闭 reporting：

```bash
bash motivation/experiments/exp3-RL-fork/systems/agentenv/set-balloon.sh off
# 随后运行 Exp3 时显式设置 BALLOON_MODE=off
# 完成该组后，如需恢复默认：
bash motivation/experiments/exp3-RL-fork/systems/agentenv/set-balloon.sh on
```

两次切换都要求无活跃 sandbox，并会重启 server。关闭后必须使用新冷启动实例；已有 snapshot 不能用于验证新配置。`BALLOON_MODE` 本身不修改 server。

## 可选：只读 lower 的 Direct I/O

这是 Exp1 的独立变体，不是所有实验的必要步骤：

```bash
bash motivation/experiments/run.sh agentenv prettier-14400 enable-direct-io
EXPECTED_OVERLAYBD_IO_ENGINE=2 \
  bash motivation/experiments/run.sh agentenv prettier-14400
bash motivation/experiments/run.sh agentenv prettier-14400 disable-direct-io
```

启用脚本备份 ublk daemon 并安装 wrapper，在 server 生成配置后将 `ioEngine` 改为 2，重启后验证；回退脚本恢复原二进制。runner 将实际配置写入 raw，预期值不符时拒绝运行。它仅绕过 host 的本地只读 lower data cache，guest page cache、upper 和 index 仍存在。

## 清理与排错

- `aenv list` 必须为空才开始正式测量；采集器统计的是整个 AgentENV 服务 cgroup。
- Exp1/2 可经公共入口执行对应 `cleanup`；清理只依据本实验记录的 ID，不删除 raw。
- Exp3 正常退出时由 controller 清理实例和 snapshot。若强制中断，按 raw 的 `sandbox-ids.tsv`、`events.tsv` 核对残留；检查 `cleanup-errors.log`，不要按名称批量删除无关模板。
- 健康检查失败先查 `docker logs aenv-server`；balloon 校验失败先确认容器运行的是本地源码构建，并且已执行切换脚本。
