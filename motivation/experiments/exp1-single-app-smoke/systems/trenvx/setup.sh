#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
experiment_root="${MIXFS_EXPERIMENT_ROOT:-$(cd -- "$script_dir/../.." && pwd)}"
repo_root="$(cd -- "$experiment_root/../../.." && pwd)"
trenv_root="$repo_root/baselines/TrEnv-X"
# shellcheck source=config.env
source "$script_dir/config.env"

if [[ ${CONDA_DEFAULT_ENV:-} != hybridfs ]]; then
  echo 'activate the hybridfs conda environment first' >&2
  exit 1
fi
for tool in cargo docker git go make rustup sudo; do
  command -v "$tool" >/dev/null || { echo "missing command: $tool" >&2; exit 1; }
done
[[ $(go env GOVERSION) == go1.23.* ]] || { echo "Go 1.23 is required, got $(go env GOVERSION)" >&2; exit 1; }
rustup run "$CH_RUST_TOOLCHAIN" rustc --version >/dev/null
sudo -n true
test -r /dev/kvm && test -w /dev/kvm
# iptables uses a host-global lock even when rules are changed from a network
# namespace.  TrEnv-X runs unprivileged with capabilities, so grant only this
# user access to the lock instead of running the whole orchestrator as root.
sudo touch /run/xtables.lock
sudo setfacl -m "u:$USER:rw" /run/xtables.lock

"$experiment_root/workloads/${MIXFS_WORKLOAD_NAME:-$WORKLOAD_NAME}/build-manifest.sh"
docker build -f "$script_dir/Dockerfile" \
  --build-arg "WORKLOAD_IMAGE=$WORKLOAD_IMAGE" \
  -t "$DERIVED_IMAGE" "$experiment_root"

if [[ ! -d $CH_SOURCE/.git ]]; then
  mkdir -p "$(dirname "$CH_SOURCE")"
  git clone --branch ci --single-branch \
    https://github.com/X-code-interpreter/cloud-hypervisor.git "$CH_SOURCE"
fi
git -C "$CH_SOURCE" fetch origin ci
git -C "$CH_SOURCE" checkout --detach "$CH_COMMIT"
# Pin the compiler generation used by this v45-era tree.  Newer libc/syscall
# code generation can trip its static seccomp allow-list even on VmmPing.
rustup run "$CH_RUST_TOOLCHAIN" cargo build \
  --manifest-path "$CH_SOURCE/Cargo.toml" --release --bin cloud-hypervisor

for component in envd orchestrator cli template-manager; do
  make -C "$trenv_root/packages/$component" build
done

kernel="$DATA_ROOT/kernels/$KERNEL_VERSION/vmlinux"
if [[ ! -s $kernel ]]; then
  "$script_dir/build-kernel.sh"
fi
python -m pip install -e "$trenv_root/sandbox-sdk"

template_dir="$DATA_ROOT/templates/$TEMPLATE_ID"
if [[ -e $template_dir ]]; then
  if [[ ${REBUILD_TEMPLATE:-0} != 1 ]]; then
    echo "template already exists: $template_dir (set REBUILD_TEMPLATE=1 to replace it)" >&2
    exit 1
  fi
  rm -rf -- "$template_dir"
fi
"$trenv_root/packages/template-manager/bin/template-manager" --config "$script_dir/config.toml"

{
  printf 'created_utc=%s\n' "$(date -u --iso-8601=seconds)"
  printf 'workload_image=%s\n' "$WORKLOAD_IMAGE"
  printf 'derived_image=%s\n' "$DERIVED_IMAGE"
  printf 'trenvx_commit=%s\n' "$(git -C "$trenv_root" rev-parse HEAD)"
  printf 'cloud_hypervisor_commit=%s\n' "$(git -C "$CH_SOURCE" rev-parse HEAD)"
  printf 'cloud_hypervisor_rust_toolchain=%s\n' "$CH_RUST_TOOLCHAIN"
  printf 'kernel_sha256=%s\n' "$(sha256sum "$kernel" | awk '{print $1}')"
  printf 'rootfs_sha256=%s\n' "$(sha256sum "$template_dir/image/rootfs.ext4" | awk '{print $1}')"
} > "$template_dir/provenance.env"

echo "template ready: $template_dir"
