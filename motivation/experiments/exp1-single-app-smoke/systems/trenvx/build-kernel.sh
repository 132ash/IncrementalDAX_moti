#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
experiment_root="${MIXFS_EXPERIMENT_ROOT:-$(cd -- "$script_dir/../.." && pwd)}"
repo_root="$(cd -- "$experiment_root/../../.." && pwd)"
# shellcheck source=config.env
source "$script_dir/config.env"

[[ ${CONDA_DEFAULT_ENV:-} == hybridfs ]] || {
  echo 'activate the hybridfs conda environment first' >&2
  exit 1
}
for tool in bc bison flex gcc git make; do
  command -v "$tool" >/dev/null || { echo "missing kernel build command: $tool" >&2; exit 1; }
done

version="${KERNEL_VERSION#ch-}"
[[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
  echo "invalid CH kernel version: $KERNEL_VERSION" >&2
  exit 1
}
source_dir="$DATA_ROOT/deps/linux-$version"
output_dir="$DATA_ROOT/kernels/$KERNEL_VERSION"
config="$repo_root/baselines/TrEnv-X/packages/fc-kernels/configs/ch-6.1.config"

if [[ ! -d $source_dir/.git ]]; then
  mkdir -p "$(dirname "$source_dir")"
  git clone --depth 1 --branch "v$version" \
    https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git "$source_dir"
fi
[[ $(git -C "$source_dir" describe --tags --exact-match) == "v$version" ]] || {
  echo "kernel source is not at v$version: $source_dir" >&2
  exit 1
}

make -C "$source_dir" mrproper
cp "$config" "$source_dir/.config"
make -C "$source_dir" olddefconfig
make -C "$source_dir" -j"$(nproc)" vmlinux
mkdir -p "$output_dir"
install -m 0664 "$source_dir/vmlinux" "$output_dir/vmlinux"
sha256sum "$output_dir/vmlinux"
