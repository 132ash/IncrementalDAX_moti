#!/usr/bin/env bash
set -euo pipefail

round=${ROUND:?ROUND is required}
actions_root=${ACTIONS_ROOT:-/opt/mixfs/rounds}
out=${OUTPUT_DIR:-/tmp/mixfs-exp2/round-$round}
timeout_seconds=${ACTION_TIMEOUT_SECONDS:-300}
sample_interval=${MEMORY_SAMPLE_INTERVAL_SECONDS:-0.02}
actions="$actions_root/$round/actions"

test -d "$actions"
mkdir -p "$out/stdout" "$out/stderr"
printf 'round\tstep\texit_code\tduration_ns\n' > "$out/steps.tsv"
printf 'timestamp_ns\tphase\tround\tstep\tMemTotal_kib\tMemFree_kib\tBuffers_kib\tCached_kib\tShmem_kib\n' > "$out/guest-memory.tsv"

sample_memory() {
  local phase=$1 step=$2 timestamp_ns
  timestamp_ns="$(date +%s%N)"
  awk -v ts="$timestamp_ns" -v phase="$phase" -v round="$round" -v step="$step" '
    BEGIN {
      split("MemTotal MemFree Buffers Cached Shmem", wanted)
      for (i in wanted) keep[wanted[i]]=1
    }
    $1 ~ /:$/ { key=$1; sub(/:$/, "", key); if (key in keep) value[key]=$2 }
    END { printf "%s\t%s\t%s\t%s",ts,phase,round,step; for(i=1;i<=5;i++) printf "\t%s",value[wanted[i]]+0; printf "\n" }
  ' /proc/meminfo >> "$out/guest-memory.tsv"
}

monitor_step() {
  while :; do sample_memory running "$1"; sleep "$sample_interval"; done
}

sample_memory baseline 000
for action in "$actions"/*.sh; do
  step="$(basename "$action" .sh)"
  sample_memory before "$step"
  monitor_step "$step" & monitor_pid=$!
  # CLOCK_REALTIME jumps after a restored guest resynchronizes its wall clock.
  # CLOCK_MONOTONIC remains stable across the action measurement window.
  start_ns="$(python3 -c 'import time; print(time.monotonic_ns())')"
  set +e
  (cd /testbed && timeout --signal=TERM --kill-after=10s "${timeout_seconds}s" bash "$action") > "$out/stdout/$step.log" 2> "$out/stderr/$step.log"
  status=$?
  set -e
  end_ns="$(python3 -c 'import time; print(time.monotonic_ns())')"
  kill "$monitor_pid" 2>/dev/null || true
  wait "$monitor_pid" 2>/dev/null || true
  sample_memory after "$step"
  printf '%s\t%s\t%s\t%s\n' "$round" "$step" "$status" "$((end_ns-start_ns))" >> "$out/steps.tsv"
done

git -C /testbed status --porcelain=v1 > "$out/git-status.txt"
git -C /testbed diff --binary > "$out/patch.diff"
cp "$actions_root/$round/actions.tsv" "$out/actions.tsv"
sample_memory complete 999
