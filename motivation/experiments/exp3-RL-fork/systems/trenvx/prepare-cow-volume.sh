#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$script_dir/config.env"
volume=/var/lib/trenvx-exp5-cow.img
if [[ ! -e $volume ]]; then
  sudo -n truncate -s 100G "$volume"
  sudo -n mkfs.btrfs -f -q "$volume"
fi
sudo -n mkdir -p "$DATA_ROOT"
if ! mountpoint -q "$DATA_ROOT"; then
  device="$(sudo -n losetup -j "$volume" | cut -d: -f1 | head -1)"
  if [[ -z $device ]]; then
    device="$(sudo -n losetup -f --show --direct-io=on "$volume")"
  fi
  sudo -n mount -o noatime,compress=no "$device" "$DATA_ROOT"
fi
[[ $(stat -f -c %T "$DATA_ROOT") == btrfs ]] || { echo "not btrfs: $DATA_ROOT" >&2; exit 1; }
sudo -n chown "$USER:$USER" "$DATA_ROOT"
mkdir -p "$DATA_ROOT/templates"
if [[ ! -e $DATA_ROOT/kernels ]]; then
  ln -s /var/lib/trenvx/kernels "$DATA_ROOT/kernels"
fi
