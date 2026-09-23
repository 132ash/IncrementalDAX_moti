#!/usr/bin/env bash
set -euo pipefail

actions=${ACTIONS_DIR:-/opt/mixfs/actions}
out=${OUTPUT_DIR:-/tmp/mixfs-replay}
timeout_seconds=${ACTION_TIMEOUT_SECONDS:-60}
sample_interval=${MEMORY_SAMPLE_INTERVAL_SECONDS:-0.02}
drop_caches=${DROP_GUEST_CACHES:-1}

mkdir -p "$out/stdout" "$out/stderr"
printf 'step\texit_code\tduration_ns\n' > "$out/steps.tsv"
printf '%s\n' \
  $'timestamp_ns\tphase\tstep\tMemTotal_kib\tMemFree_kib\tMemAvailable_kib\tBuffers_kib\tCached_kib\tSReclaimable_kib\tShmem_kib\tAnonPages_kib\tSlab_kib\tSUnreclaim_kib\tKernelStack_kib\tPageTables_kib\tPercpu_kib' \
  > "$out/guest-memory.tsv"
printf '%s\n' $'timestamp_ns\tphase\tstep\tpgfault\tpgmajfault\tpgpgin\tpgpgout' \
  > "$out/guest-vmstat.tsv"

sample_memory() {
  local phase=$1 step=$2 timestamp_ns
  timestamp_ns="$(date +%s%N)"
  awk -v timestamp_ns="$timestamp_ns" -v phase="$phase" -v step="$step" '
    BEGIN {
      split("MemTotal MemFree MemAvailable Buffers Cached SReclaimable Shmem AnonPages Slab SUnreclaim KernelStack PageTables Percpu", wanted)
      for (i in wanted) keep[wanted[i]]=1
    }
    $1 ~ /:$/ {
      key=$1; sub(/:$/, "", key)
      if (key in keep) value[key]=$2
    }
    END {
      printf "%s\t%s\t%s", timestamp_ns, phase, step
      for (i=1; i<=13; i++) printf "\t%s", value[wanted[i]]+0
      printf "\n"
    }
  ' /proc/meminfo >> "$out/guest-memory.tsv"
  awk -v timestamp_ns="$timestamp_ns" -v phase="$phase" -v step="$step" '
    $1 == "pgfault" || $1 == "pgmajfault" || $1 == "pgpgin" || $1 == "pgpgout" { value[$1]=$2 }
    END { printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\n", timestamp_ns, phase, step, value["pgfault"]+0, value["pgmajfault"]+0, value["pgpgin"]+0, value["pgpgout"]+0 }
  ' /proc/vmstat >> "$out/guest-vmstat.tsv"
}

monitor_step() {
  local step=$1
  while :; do
    sample_memory running "$step"
    sleep "$sample_interval"
  done
}

{
  date -u --iso-8601=seconds
  uname -a
  printf 'project_node='; node --version
  printf 'original_head='; git -C /testbed rev-parse HEAD
  printf 'memory_limit_mib=%s\n' "$(awk '/MemTotal:/ { printf "%.0f", $2 / 1024 }' /proc/meminfo)"
  printf 'drop_guest_caches=%s\n' "$drop_caches"
  printf 'sample_interval_seconds=%s\n' "$sample_interval"
} > "$out/environment.txt"
cat /proc/cmdline > "$out/proc-cmdline.txt"
findmnt -o TARGET,SOURCE,FSTYPE,OPTIONS > "$out/findmnt.txt"
lsblk -o NAME,TYPE,SIZE,ROTA,RO,MOUNTPOINTS > "$out/lsblk.txt"

git -C /testbed add -A
git -C /testbed write-tree > "$out/baseline-tree.txt"
git -C /testbed reset --mixed >/dev/null
git -C /testbed rev-parse HEAD > "$out/original-head.txt"

if [[ $drop_caches == 1 ]]; then
  sync
  echo 3 > /proc/sys/vm/drop_caches
fi
sample_memory baseline 000
sample_memory baseline 000

for action in "$actions"/*.sh; do
  step="$(basename "$action" .sh)"
  sample_memory before "$step"
  monitor_step "$step" &
  monitor_pid=$!
  start_ns="$(date +%s%N)"
  set +e
  (cd /testbed && timeout --signal=TERM --kill-after=5s "${timeout_seconds}s" bash "$action") \
    > "$out/stdout/$step.log" 2> "$out/stderr/$step.log"
  status=$?
  set -e
  end_ns="$(date +%s%N)"
  kill "$monitor_pid" 2>/dev/null || true
  wait "$monitor_pid" 2>/dev/null || true
  sample_memory after "$step"
  printf '%s\t%s\t%s\n' "$step" "$status" "$((end_ns - start_ns))" \
    >> "$out/steps.tsv"
done

git -C /testbed add -A
git -C /testbed diff --binary --cached "$(cat "$out/baseline-tree.txt")" > "$out/patch.diff"
git -C /testbed reset --mixed >/dev/null
git -C /testbed status --porcelain=v1 > "$out/git-status.txt"
cp "${actions}.tsv" "$out/actions.tsv"
sample_memory complete 999
