# 部署说明

本实验复用仓库已有 AgentENV Docker 部署，不另建第二套 server。完整安装原理和安全边界
见：

- [`docs/deployment/agentenv-claude-code-deepseek.md`](../../../../../docs/deployment/agentenv-claude-code-deepseek.md)
- [`docs/deployment/workload-prettier-14400.md`](../../../../../docs/deployment/workload-prettier-14400.md)

固定 action replay 本身不需要 Claude Code 或 DeepSeek key。最小部署检查为：

```bash
test "$(uname -m)" = x86_64
test -r /dev/kvm && test -w /dev/kvm
docker ps --filter name=aenv-server
curl -fsS http://127.0.0.1:8000/health
aenv --version
aenv list
sudo -n true
```

若 server 尚未部署，按上面的主部署文档执行 Docker 或 systemd 二选一流程并完成
`aenv auth`。本机当前实验使用名为 `aenv-server` 的 Docker 容器；host 内存采样器也以
该容器名定位 cgroup。若改变容器名，应同步调整公共采样器。

实验固定使用 digest，而不是 registry 的浮动 tag。首次运行会由 AgentENV 解析/缓存
镜像，冷启动时间可能包含额外下载；正式性能重复应明确区分首次拉取与已缓存运行。

部署成功后运行：

```bash
cd /home/shao/MixFS
bash motivation/experiments/run.sh agentenv prettier-14400
```

runner 会自己创建一次性 cold-start sandbox，不要求预建 template/snapshot，结束后自动
删除 sandbox。它不会删除 AgentENV server、镜像 cache 或 workload 输入。
