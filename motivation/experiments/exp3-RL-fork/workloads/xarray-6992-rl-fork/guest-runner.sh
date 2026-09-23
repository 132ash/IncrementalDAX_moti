#!/usr/bin/env bash
set -euo pipefail

round=${ROUND:?ROUND is required}
branch=${BRANCH:?BRANCH is required}
sandbox_label=${SANDBOX_LABEL:-$branch}
actions_root=${ACTIONS_ROOT:?ACTIONS_ROOT is required}
out=${OUTPUT_DIR:?OUTPUT_DIR is required}
timeout_seconds=${ACTION_TIMEOUT_SECONDS:-300}
sample_interval=${MEMORY_SAMPLE_INTERVAL_SECONDS:-0.05}
manifest="$actions_root/$round/actions.tsv"

test -s "$manifest"
mkdir -p "$out/stdout" "$out/stderr"
printf 'sandbox\tbranch\tround\tstep\texit_code\tduration_ns\n' > "$out/steps.tsv"
printf 'timestamp_ns\tphase\tsandbox\tbranch\tround\tstep\tMemTotal_kib\tMemFree_kib\tBuffers_kib\tCached_kib\tShmem_kib\tAnonPages_kib\tActive_file_kib\tInactive_file_kib\tDirty_kib\n' > "$out/guest-memory.tsv"
printf 'timestamp_ns\tphase\tsandbox\tbranch\tround\tstep\tpgfault\tpgmajfault\tpgpgin\tpgpgout\n' > "$out/guest-vmstat.tsv"
export BRANCH ROUND
export MIXFS_WORKLOAD_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

sample_memory() {
  local phase=$1 step=$2 timestamp_ns
  timestamp_ns="$(date +%s%N)"
  awk -v ts="$timestamp_ns" -v phase="$phase" -v sandbox="$sandbox_label" -v branch="$branch" -v round="$round" -v step="$step" '
    BEGIN { split("MemTotal MemFree Buffers Cached Shmem AnonPages Active_file Inactive_file Dirty", wanted); for (i in wanted) keep[wanted[i]]=1 }
    $1 ~ /:$/ { key=$1; sub(/:$/, "", key); gsub(/[()]/, "_", key); sub(/_$/, "", key); if (key in keep) value[key]=$2 }
    END { printf "%s\t%s\t%s\t%s\t%s\t%s",ts,phase,sandbox,branch,round,step; for(i=1;i<=9;i++) printf "\t%s",value[wanted[i]]+0; printf "\n" }
  ' /proc/meminfo >> "$out/guest-memory.tsv"
}

sample_vmstat() {
  local phase=$1 step=$2 timestamp_ns
  timestamp_ns="$(date +%s%N)"
  awk -v ts="$timestamp_ns" -v phase="$phase" -v sandbox="$sandbox_label" -v branch="$branch" -v round="$round" -v step="$step" '
    BEGIN { split("pgfault pgmajfault pgpgin pgpgout", wanted); for (i in wanted) keep[wanted[i]]=1 }
    $1 in keep { value[$1]=$2 }
    END { printf "%s\t%s\t%s\t%s\t%s\t%s",ts,phase,sandbox,branch,round,step; for(i=1;i<=4;i++) printf "\t%s",value[wanted[i]]+0; printf "\n" }
  ' /proc/vmstat >> "$out/guest-vmstat.tsv"
}

monitor_step() { while :; do sample_memory running "$1"; sleep "$sample_interval"; done; }

sample_memory baseline 000
sample_vmstat baseline 000
if [[ $round == 3 ]]; then
  python3 "$MIXFS_WORKLOAD_ROOT/cache-residency.py" /testbed > "$out/cache-residency-before.tsv"
fi
while IFS=$'\t' read -r step expected_hash command; do
  [[ $step == step ]] && continue
  actual_hash="$(printf '%s' "$command" | sha256sum | awk '{print $1}')"
  [[ $actual_hash == "$expected_hash" ]] || { echo "manifest hash mismatch at step $step" >&2; exit 1; }
  sample_memory before "$step"
  sample_vmstat before "$step"
  monitor_step "$step" & monitor_pid=$!
  start_ns="$(python3 -c 'import time; print(time.monotonic_ns())')"
  set +e
  (cd /testbed && timeout --signal=TERM --kill-after=10s "${timeout_seconds}s" bash -o pipefail -c "$command") > "$out/stdout/$step.log" 2> "$out/stderr/$step.log"
  status=$?
  set -e
  end_ns="$(python3 -c 'import time; print(time.monotonic_ns())')"
  kill "$monitor_pid" 2>/dev/null || true
  wait "$monitor_pid" 2>/dev/null || true
  sample_memory after "$step"
  sample_vmstat after "$step"
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$sandbox_label" "$branch" "$round" "$step" "$status" "$((end_ns-start_ns))" >> "$out/steps.tsv"
done < "$manifest"

git -C /testbed status --porcelain=v1 > "$out/git-status.txt"
git -C /testbed diff --binary > "$out/patch.diff"
cp "$manifest" "$out/actions.tsv"
if [[ $round == 3 ]]; then
  python3 "$MIXFS_WORKLOAD_ROOT/cache-residency.py" /testbed > "$out/cache-residency-after.tsv"
fi
sample_memory complete 999
sample_vmstat complete 999
