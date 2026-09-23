#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
experiment_root="${MIXFS_EXPERIMENT_ROOT:-$(cd -- "$script_dir/../.." && pwd)}"
repo_root="$(cd -- "$experiment_root/../../.." && pwd)"
source "$script_dir/config.env"

cache_mode=${AGENTENV_CACHE_MODE:-preserve}
[[ $cache_mode == preserve || $cache_mode == drop ]] || { echo "invalid AGENTENV_CACHE_MODE: $cache_mode" >&2; exit 2; }
workload_root="$experiment_root/workloads/${MIXFS_WORKLOAD_NAME:-$WORKLOAD_NAME}"
output_root="${OUTPUT_ROOT:-$repo_root/motivation/results/exp2-multi-rounds/agentenv-$cache_mode-cache}"
run_id="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)-agentenv-$cache_mode}"
raw_dir="$output_root/raw/$run_id"
lock_file="$output_root/.run.lock"
sandbox_id=''
snapshot_aliases=()

mkdir -p "$output_root/raw" "$output_root/figures"
exec 9> "$lock_file"
flock -n 9 || { echo "another run holds $lock_file" >&2; exit 1; }
[[ ! -e $raw_dir ]] || { echo "run directory exists: $raw_dir" >&2; exit 1; }
mkdir -p "$raw_dir/rounds"

cleanup() {
  if [[ -n $sandbox_id ]]; then aenv delete "$sandbox_id" >> "$raw_dir/cleanup.log" 2>&1 || true; fi
  for ((i=${#snapshot_aliases[@]}-1; i>=0; i--)); do aenv template delete "${snapshot_aliases[i]}" >> "$raw_dir/cleanup.log" 2>&1 || true; done
}
trap cleanup EXIT INT TERM

for tool in aenv flock jq python3 sha256sum; do command -v "$tool" >/dev/null || { echo "missing command: $tool" >&2; exit 1; }; done
test "$(uname -m)" = x86_64
test "$(aenv list | jq 'length')" = 0 || { echo 'active AgentENV sandboxes exist' >&2; exit 1; }
"$workload_root/build-manifests.sh"
for round in 1 2 3 4; do test "$(find "$workload_root/rounds/$round/actions" -name '*.sh' | wc -l)" = 8; done

{
  printf 'run_id=%s\nsystem=agentenv\ncache_mode=%s\nworkload_image=%s\n' "$run_id" "$cache_mode" "$WORKLOAD_IMAGE"
  printf 'sandbox_cpu=%s\nsandbox_memory_mib=%s\nstarted_utc=%s\n' "$SANDBOX_CPU" "$SANDBOX_MEMORY_MIB" "$(date -u --iso-8601=seconds)"
  printf 'rounds_sha256=%s\n' "$(find "$workload_root/rounds" -name actions.tsv -print0 | sort -z | xargs -0 sha256sum | sha256sum | awk '{print $1}')"
  printf 'latency_scope=actions_only\ntransition_latency_included=false\n'
} > "$raw_dir/metadata.env"
printf 'after_round\tcheckpoint_ns\trestore_ns\timage_rebuild_ns\n' > "$raw_dir/transitions.tsv"

# Initial creation is deliberately outside the measurement window.
sandbox_id="$(aenv start --cold "$WORKLOAD_IMAGE" --detach --timeout "$SANDBOX_TIMEOUT_SECONDS" --cpu "$SANDBOX_CPU" --memory "$SANDBOX_MEMORY_MIB")"
printf '%s\n' "$sandbox_id" >> "$raw_dir/sandbox-ids.txt"
for _ in $(seq 1 60); do aenv exec "$sandbox_id" true >/dev/null 2>&1 && break; sleep 1; done
aenv exec "$sandbox_id" true
aenv upload "$sandbox_id" "$workload_root/rounds" /workspace/mixfs-rounds
aenv upload "$sandbox_id" "$workload_root/guest-runner.sh" /workspace/mixfs-guest-runner.sh

for round in 1 2 3 4; do
  aenv exec "$sandbox_id" bash -lc "ROUND='$round' ACTIONS_ROOT=/workspace/mixfs-rounds ACTION_TIMEOUT_SECONDS='$ACTION_TIMEOUT_SECONDS' MEMORY_SAMPLE_INTERVAL_SECONDS='$MEMORY_SAMPLE_INTERVAL_SECONDS' OUTPUT_DIR='/workspace/artifacts/$round' bash /workspace/mixfs-guest-runner.sh"
  aenv download "$sandbox_id" "/workspace/artifacts/$round" "$raw_dir/rounds"
  test -s "$raw_dir/rounds/$round/steps.tsv"
  if [[ $cache_mode == drop ]]; then
    aenv exec "$sandbox_id" bash -lc 'sync; echo 3 > /proc/sys/vm/drop_caches'
  fi

  alias="mixfs-exp2-${run_id//[^a-zA-Z0-9-]/-}-r$round"
  snapshot_aliases+=("$alias")
  start_ns="$(date +%s%N)"
  aenv snapshot create "$sandbox_id" --name "$alias" > "$raw_dir/rounds/$round/checkpoint.log"
  checkpoint_ns="$(($(date +%s%N)-start_ns))"
  aenv delete "$sandbox_id" >> "$raw_dir/cleanup.log" 2>&1
  sandbox_id=''

  start_ns="$(date +%s%N)"
  sandbox_id="$(aenv start "$alias" --detach --timeout "$SANDBOX_TIMEOUT_SECONDS")"
  for _ in $(seq 1 60); do aenv exec "$sandbox_id" true >/dev/null 2>&1 && break; sleep 1; done
  aenv exec "$sandbox_id" true
  restore_ns="$(($(date +%s%N)-start_ns))"
  printf '%s\t%s\t%s\t0\n' "$round" "$checkpoint_ns" "$restore_ns" >> "$raw_dir/transitions.tsv"
  printf '%s\n' "$sandbox_id" >> "$raw_dir/sandbox-ids.txt"
done

oracle_status=0
grep -F 'type G = (A & B)[keyof C];' "$raw_dir/rounds/4/stdout/004.log" > "$raw_dir/oracle-matches.txt" || oracle_status=1
printf '%s\n' "$oracle_status" > "$raw_dir/oracle-exit-code.txt"
aenv delete "$sandbox_id" >> "$raw_dir/cleanup.log" 2>&1
sandbox_id=''
for ((i=${#snapshot_aliases[@]}-1; i>=0; i--)); do aenv template delete "${snapshot_aliases[i]}" >> "$raw_dir/cleanup.log" 2>&1; done
snapshot_aliases=()
printf '%s\n' "$run_id" > "$output_root/latest-run.txt"
python3 "$experiment_root/analyze.py" "$output_root"
echo "raw result: $raw_dir"
echo "summary:    $output_root/summary.md"
exit "$oracle_status"
