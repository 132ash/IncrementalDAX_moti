#!/usr/bin/env bash
set -euo pipefail

real_daemon=/usr/local/bin/uvm-ublk-daemon.buffered
global_config=''
resize_config=''
previous=''
for argument in "$@"; do
  case "$previous" in
    --global-config) global_config=$argument ;;
    --resize-global-config) resize_config=$argument ;;
  esac
  previous=$argument
done

for config_path in "$global_config" "$resize_config"; do
  [[ -n $config_path && -f $config_path ]] || continue
  sed -i 's/"ioEngine": 0/"ioEngine": 2/' "$config_path"
  grep -q '"ioEngine": 2' "$config_path" || {
    echo "failed to enable direct I/O in $config_path" >&2
    exit 1
  }
done

exec "$real_daemon" "$@"
