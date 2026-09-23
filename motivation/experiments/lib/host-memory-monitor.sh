#!/usr/bin/env bash
set -euo pipefail

if (($# != 3)); then
  echo "usage: $0 OUTPUT_TSV PHASE_FILE INTERVAL_SECONDS" >&2
  exit 2
fi

output=$1
phase_file=$2
interval=$3

container_pid="$(docker inspect aenv-server --format '{{.State.Pid}}')"
cgroup_rel="$(awk -F: '$1 == "0" { print $3 }' "/proc/$container_pid/cgroup")"
cgroup_dir="/sys/fs/cgroup${cgroup_rel}"
test -r "$cgroup_dir/memory.current"
test -r "$cgroup_dir/memory.stat"

printf '%s\n' \
  $'timestamp_ns\tphase\tcgroup_current_bytes\tcgroup_anon_bytes\tcgroup_file_bytes\tcgroup_kernel_bytes\tfirecracker_pid\tfirecracker_rss_kib\tfirecracker_pss_kib\tfirecracker_anon_kib\tfirecracker_file_kib' \
  > "$output"

while :; do
  timestamp_ns="$(date +%s%N)"
  phase="$(cat "$phase_file" 2>/dev/null || printf unknown)"
  current="$(cat "$cgroup_dir/memory.current")"
  read -r anon file kernel < <(
    awk '
      $1 == "anon" { anon=$2 }
      $1 == "file" { file=$2 }
      $1 == "kernel" { kernel=$2 }
      END { printf "%s %s %s\n", anon+0, file+0, kernel+0 }
    ' "$cgroup_dir/memory.stat"
  )

  best_pid=0
  best_rss=0
  best_pss=0
  best_anon=0
  best_file=0
  while read -r pid; do
    [[ $pid =~ ^[0-9]+$ ]] || continue
    rollup="$(sudo -n awk '
      $1 == "Rss:" { rss=$2 }
      $1 == "Pss:" { pss=$2 }
      $1 == "Pss_Anon:" { anon=$2 }
      $1 == "Pss_File:" { file=$2 }
      END { printf "%s %s %s %s\n", rss+0, pss+0, anon+0, file+0 }
    ' "/proc/$pid/smaps_rollup" 2>/dev/null || printf '0 0 0 0')"
    read -r rss pss proc_anon proc_file <<< "$rollup"
    if ((rss > best_rss)); then
      best_pid=$pid
      best_rss=$rss
      best_pss=$pss
      best_anon=$proc_anon
      best_file=$proc_file
    fi
  done < <(pgrep -x firecracker || true)

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$timestamp_ns" "$phase" "$current" "$anon" "$file" "$kernel" \
    "$best_pid" "$best_rss" "$best_pss" "$best_anon" "$best_file" \
    >> "$output"
  sleep "$interval"
done
