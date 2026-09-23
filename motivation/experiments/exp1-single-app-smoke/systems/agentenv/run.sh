#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
experiment_root="${MIXFS_EXPERIMENT_ROOT:-$(cd -- "$script_dir/../.." && pwd)}"
repo_root="$(cd -- "$experiment_root/../../.." && pwd)"
# shellcheck source=config.env
source "$script_dir/config.env"

workload_root="${WORKLOAD_ROOT:-$experiment_root/workloads/${MIXFS_WORKLOAD_NAME:-$WORKLOAD_NAME}}"
output_root="${OUTPUT_ROOT:-$repo_root/$OUTPUT_REL}"
run_id="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)-agentenv-replay}"
raw_dir="$output_root/raw/$run_id"
host_dir="$raw_dir/host"
phase_file="$raw_dir/.host-monitor-phase"
lock_file="$output_root/.run.lock"
sandbox_id=''
monitor_pid=''
exec_status=1

mkdir -p "$output_root/raw" "$output_root/figures"
exec 9> "$lock_file"
flock -n 9 || { echo "another experiment run holds $lock_file" >&2; exit 1; }
if [[ -e $raw_dir ]]; then
  echo "run directory already exists: $raw_dir" >&2
  exit 1
fi
mkdir -p "$host_dir"

cleanup_runtime() {
  if [[ -n $monitor_pid ]]; then
    kill "$monitor_pid" 2>/dev/null || true
    wait "$monitor_pid" 2>/dev/null || true
  fi
  rm -f "$phase_file"
  if [[ -n $sandbox_id && ${KEEP_SANDBOX:-0} != 1 ]]; then
    if aenv delete "$sandbox_id" >> "$raw_dir/cleanup.log" 2>&1; then
      printf 'deleted=%s\n' "$sandbox_id" >> "$raw_dir/cleanup.log"
    else
      printf 'delete_failed=%s\n' "$sandbox_id" >> "$raw_dir/cleanup.log"
    fi
  fi
}
trap cleanup_runtime EXIT INT TERM

for tool_name in aenv awk column docker flock jq pgrep python3 sudo; do
  command -v "$tool_name" >/dev/null || { echo "missing command: $tool_name" >&2; exit 1; }
done
sudo -n true || { echo 'passwordless sudo is required for Firecracker smaps sampling' >&2; exit 1; }
test "$(uname -m)" = x86_64 || { echo 'the fixed workload image requires x86_64' >&2; exit 1; }
test -d "$workload_root/actions"
test "$(find "$workload_root/actions" -maxdepth 1 -name '*.sh' | wc -l)" = 26
test -s "$workload_root/actions.tsv"
test "$(aenv list | jq 'length')" = 0 || {
  echo 'active AgentENV sandboxes exist; refusing an attribution-ambiguous run' >&2
  exit 1
}
test "$(docker inspect aenv-server --format '{{.State.Running}}')" = true
overlaybd_config="$(docker exec aenv-server cat /workspace/env/overlaybd/overlaybd-global.json)"
overlaybd_io_engine="$(jq -er '.ioEngine' <<< "$overlaybd_config")"
if [[ -n $EXPECTED_OVERLAYBD_IO_ENGINE && $overlaybd_io_engine != "$EXPECTED_OVERLAYBD_IO_ENGINE" ]]; then
  echo "expected OverlayBD ioEngine=$EXPECTED_OVERLAYBD_IO_ENGINE, got $overlaybd_io_engine" >&2
  exit 1
fi
printf '%s\n' "$overlaybd_config" > "$raw_dir/overlaybd-global.json"

{
  printf 'run_id=%s\n' "$run_id"
  printf 'started_utc=%s\n' "$(date -u --iso-8601=seconds)"
  printf 'workload_image=%s\n' "$WORKLOAD_IMAGE"
  printf 'sandbox_cpu=%s\n' "$SANDBOX_CPU"
  printf 'sandbox_memory_mib=%s\n' "$SANDBOX_MEMORY_MIB"
  printf 'action_manifest_sha256=%s\n' "$(sha256sum "$workload_root/actions.tsv" | awk '{print $1}')"
  printf 'aenv_version=%s\n' "$(aenv --version)"
  printf 'host_kernel=%s\n' "$(uname -r)"
  printf 'agentenv_container_image=%s\n' "$(docker inspect aenv-server --format '{{.Config.Image}}')"
  printf 'agentenv_container_id=%s\n' "$(docker inspect aenv-server --format '{{.Id}}')"
  printf 'overlaybd_io_engine=%s\n' "$overlaybd_io_engine"
  printf 'overlaybd_direct_io=%s\n' "$([[ $overlaybd_io_engine == 2 ]] && printf true || printf false)"
} > "$raw_dir/metadata.env"

start_ns="$(date +%s%N)"
sandbox_id="$(
  aenv start --cold "$WORKLOAD_IMAGE" --detach \
    --timeout "$SANDBOX_TIMEOUT_SECONDS" \
    --cpu "$SANDBOX_CPU" --memory "$SANDBOX_MEMORY_MIB" \
    2> "$raw_dir/cold-start.log"
)"
end_ns="$(date +%s%N)"
[[ $sandbox_id =~ ^[0-9a-fA-F-]{36}$ ]] || { echo "invalid sandbox id: $sandbox_id" >&2; exit 1; }
printf '%s\n' "$sandbox_id" > "$raw_dir/sandbox-id.txt"
printf '%s\n' "$((end_ns - start_ns))" > "$raw_dir/cold-start-duration-ns.txt"

for attempt in $(seq 1 60); do
  aenv exec "$sandbox_id" true >/dev/null 2>&1 && break
  sleep 1
done
aenv exec "$sandbox_id" true
aenv upload "$sandbox_id" "$workload_root/actions" /workspace/replay-actions
aenv upload "$sandbox_id" "$workload_root/actions.tsv" /workspace/replay-actions.tsv
aenv upload "$sandbox_id" "$script_dir/guest-runner.sh" /workspace/guest-runner.sh

printf 'idle\n' > "$phase_file"
"$repo_root/motivation/experiments/lib/host-memory-monitor.sh" \
  "$host_dir/memory-samples.tsv" "$phase_file" "$MEMORY_SAMPLE_INTERVAL_SECONDS" &
monitor_pid=$!
sleep 0.2
printf 'running\n' > "$phase_file"

set +e
aenv exec "$sandbox_id" bash -lc \
  "ACTION_TIMEOUT_SECONDS='$ACTION_TIMEOUT_SECONDS' MEMORY_SAMPLE_INTERVAL_SECONDS='$MEMORY_SAMPLE_INTERVAL_SECONDS' DROP_GUEST_CACHES='$DROP_GUEST_CACHES' bash /workspace/guest-runner.sh" \
  > "$raw_dir/replay-command.stdout.log" 2> "$raw_dir/replay-command.stderr.log"
exec_status=$?
set -e
printf 'done\n' > "$phase_file"
sleep 0.1
kill "$monitor_pid" 2>/dev/null || true
wait "$monitor_pid" 2>/dev/null || true
monitor_pid=''
printf '%s\n' "$exec_status" > "$raw_dir/replay-command-exit-code.txt"

aenv download "$sandbox_id" /workspace/artifacts/replay "$raw_dir/"
test -s "$raw_dir/replay/steps.tsv"
test "$(($(wc -l < "$raw_dir/replay/steps.tsv") - 1))" = 26

oracle_status=0
{
  grep -F '    document.addEventListener("DOMContentLoaded", () => {' \
    "$raw_dir/replay/stdout/024.log" || oracle_status=1
  grep -F '      const node = document.getElementById("lastStroke");' \
    "$raw_dir/replay/stdout/024.log" || oracle_status=1
} > "$raw_dir/oracle-matches.txt"
printf '%s\n' "$oracle_status" > "$raw_dir/oracle-exit-code.txt"
printf '%s\n' "$run_id" > "$output_root/latest-run.txt"

# Delete before rebuilding the report so the summary can confirm cleanup.
aenv delete "$sandbox_id" >> "$raw_dir/cleanup.log" 2>&1
printf 'deleted=%s\n' "$sandbox_id" >> "$raw_dir/cleanup.log"
sandbox_id=''

python3 "$script_dir/analyze.py" "$output_root"
echo "raw result: $raw_dir"
echo "summary:    $output_root/summary.md"
if ((exec_status != 0)); then
  exit "$exec_status"
fi
exit "$oracle_status"
