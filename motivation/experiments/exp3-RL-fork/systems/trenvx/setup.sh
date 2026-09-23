#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
experiment_root="${MIXFS_EXPERIMENT_ROOT:-$(cd -- "$script_dir/../.." && pwd)}"
repo_root="$(cd -- "$experiment_root/../../.." && pwd)"
trenv_root="$repo_root/baselines/TrEnv-X"
source "$script_dir/config.env"
"$script_dir/prepare-cow-volume.sh"
[[ ${CONDA_DEFAULT_ENV:-} == hybridfs ]] || { echo 'activate hybridfs first' >&2; exit 1; }
for tool in cargo docker git go make python rustup setfacl sudo; do command -v "$tool" >/dev/null || { echo "missing command: $tool" >&2; exit 1; }; done
sudo -n true
sudo touch /run/xtables.lock
sudo setfacl -m "u:$USER:rw" /run/xtables.lock
cgroup_root=/sys/fs/cgroup/user.slice/trenvx-exp5
if [[ ! -d $cgroup_root ]]; then
  sudo mkdir "$cgroup_root"
  sudo chown "$USER" "$cgroup_root" "$cgroup_root/cgroup.procs" "$cgroup_root/cgroup.subtree_control"
fi
for controller in $(<"$cgroup_root/cgroup.controllers"); do
  grep -qw "$controller" "$cgroup_root/cgroup.subtree_control" || printf '+%s\n' "$controller" > "$cgroup_root/cgroup.subtree_control"
done
python "$experiment_root/workloads/$WORKLOAD_NAME/plan.py"
docker build -f "$script_dir/Dockerfile" --build-arg "WORKLOAD_IMAGE=$WORKLOAD_IMAGE" \
  --build-arg "WORKLOAD_NAME=$WORKLOAD_NAME" -t "$DERIVED_IMAGE" "$experiment_root"
if [[ ! -d $CH_SOURCE/.git ]]; then
  mkdir -p "$(dirname "$CH_SOURCE")"
  git clone --branch ci --single-branch https://github.com/X-code-interpreter/cloud-hypervisor.git "$CH_SOURCE"
fi
git -C "$CH_SOURCE" fetch origin ci
git -C "$CH_SOURCE" checkout --detach "$CH_COMMIT"
rustup run "$CH_RUST_TOOLCHAIN" cargo build --manifest-path "$CH_SOURCE/Cargo.toml" --release --bin cloud-hypervisor
for component in envd orchestrator cli template-manager; do make -C "$trenv_root/packages/$component" build; done
[[ -s $DATA_ROOT/kernels/$KERNEL_VERSION/vmlinux ]] || "$script_dir/build-kernel.sh"
python -m pip install -e "$trenv_root/sandbox-sdk"
template_dir="$DATA_ROOT/templates/$TEMPLATE_ID"
if [[ -e $template_dir ]]; then
  [[ ${REBUILD_TEMPLATE:-0} == 1 ]] || { echo "template exists: $template_dir (set REBUILD_TEMPLATE=1)" >&2; exit 1; }
  rm -rf -- "$template_dir"
fi
runtime_config="$DATA_ROOT/setup-$TEMPLATE_ID.toml"
sed -e "s|^data_root = .*|data_root = \"$DATA_ROOT\"|" \
    -e "s|^template_id = .*|template_id = \"$TEMPLATE_ID\"|" \
    -e "s|^\[template\..*\]|[template.\"$TEMPLATE_ID\"]|" \
    -e "s|^docker_img = .*|docker_img = \"$DERIVED_IMAGE\"|" \
    "$script_dir/config.toml" > "$runtime_config"
"$trenv_root/packages/template-manager/bin/template-manager" --config "$runtime_config"
rm -f -- "$runtime_config"
echo "template ready: $template_dir"
