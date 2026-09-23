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
for tool in flock python sha256sum sudo; do
  command -v "$tool" >/dev/null || { echo "missing command: $tool" >&2; exit 1; }
done
sudo -n true
test -s "$DATA_ROOT/templates/$TEMPLATE_ID/image/rootfs.ext4"

output_root="${OUTPUT_ROOT:-$repo_root/$OUTPUT_REL}"
run_id="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)-trenvx-ch-dax-replay}"
raw_dir="$output_root/raw/$run_id"
host_dir="$raw_dir/host"
phase_file="$raw_dir/.host-monitor-phase"
lock_file="$output_root/.run.lock"
backend_pid='' client_pid='' monitor_pid=''

mkdir -p "$output_root/raw" "$output_root/figures"
exec 9> "$lock_file"
flock -n 9 || { echo "another experiment run holds $lock_file" >&2; exit 1; }
[[ ! -e $raw_dir ]] || { echo "run directory exists: $raw_dir" >&2; exit 1; }
mkdir -p "$host_dir"

cleanup() {
  [[ -z $monitor_pid ]] || { kill "$monitor_pid" 2>/dev/null || true; wait "$monitor_pid" 2>/dev/null || true; }
  [[ -z $client_pid ]] || { kill "$client_pid" 2>/dev/null || true; wait "$client_pid" 2>/dev/null || true; }
  if [[ -n $backend_pid ]]; then
    kill "$backend_pid" 2>/dev/null || true
    wait "$backend_pid" 2>/dev/null || true
  fi
  rm -f "$phase_file" "$raw_dir/.run-replay"
}
trap cleanup EXIT INT TERM

"$script_dir/start-backend.sh" > "$raw_dir/orchestrator.stdout.log" \
  2> "$raw_dir/orchestrator.stderr.log" &
backend_pid=$!
for _ in $(seq 1 100); do
  (exec 8<>/dev/tcp/127.0.0.1/$ORCHESTRATOR_PORT) 2>/dev/null && { exec 8>&-; break; }
  kill -0 "$backend_pid" 2>/dev/null || { echo 'orchestrator exited during startup' >&2; exit 1; }
  sleep 0.1
done
(exec 8<>/dev/tcp/127.0.0.1/$ORCHESTRATOR_PORT) 2>/dev/null
exec 8>&-

export ACTION_TIMEOUT_SECONDS MEMORY_SAMPLE_INTERVAL_SECONDS DROP_GUEST_CACHES ORCHESTRATOR_PORT
python "$script_dir/client.py" --template "$TEMPLATE_ID" --raw-dir "$raw_dir" \
  --timeout 1800 > "$raw_dir/client.stdout.log" 2> "$raw_dir/client.stderr.log" &
client_pid=$!
for _ in $(seq 1 1800); do
  [[ -s $raw_dir/sandbox-id.txt ]] && break
  kill -0 "$client_pid" 2>/dev/null || { echo 'client exited before sandbox creation' >&2; exit 1; }
  sleep 0.1
done
test -s "$raw_dir/sandbox-id.txt"
sandbox_id="$(<"$raw_dir/sandbox-id.txt")"
cgroup_dir="/sys/fs/cgroup/user.slice/trenvx/$sandbox_id"
test -r "$cgroup_dir/memory.current"

{
  printf 'run_id=%s\n' "$run_id"
  printf 'started_utc=%s\n' "$(date -u --iso-8601=seconds)"
  printf 'workload_image=%s\n' "$WORKLOAD_IMAGE"
  printf 'derived_image=%s\n' "$DERIVED_IMAGE"
  printf 'template_id=%s\n' "$TEMPLATE_ID"
  printf 'sandbox_cpu=%s\n' "$SANDBOX_CPU"
  printf 'sandbox_memory_mib=%s\n' "$SANDBOX_MEMORY_MIB"
  printf 'action_manifest_sha256=%s\n' "$(sha256sum "$experiment_root/workloads/${MIXFS_WORKLOAD_NAME:-$WORKLOAD_NAME}/actions.tsv" | awk '{print $1}')"
  printf 'trenvx_commit=%s\n' "$(git -C "$repo_root/baselines/TrEnv-X" rev-parse HEAD)"
  printf 'cloud_hypervisor_commit=%s\n' "$(git -C "$CH_SOURCE" rev-parse HEAD)"
  printf 'cloud_hypervisor_rust_toolchain=%s\n' "$CH_RUST_TOOLCHAIN"
  printf 'cloud_hypervisor_version=%s\n' "$($CH_SOURCE/target/release/cloud-hypervisor --version)"
  printf 'guest_kernel_sha256=%s\n' "$(sha256sum "$DATA_ROOT/kernels/$KERNEL_VERSION/vmlinux" | awk '{print $1}')"
  printf 'host_kernel=%s\n' "$(uname -r)"
  printf 'host_data_fstype=%s\n' "$(findmnt -n -o FSTYPE -T "$DATA_ROOT")"
  if [[ -s $DATA_ROOT/templates/$TEMPLATE_ID/provenance.env ]]; then
    sed 's/^/template_/' "$DATA_ROOT/templates/$TEMPLATE_ID/provenance.env"
  fi
} > "$raw_dir/metadata.env"

printf 'idle\n' > "$phase_file"
"$repo_root/motivation/experiments/lib/host-cgroup-memory-monitor.sh" \
  "$host_dir/memory-samples.tsv" "$phase_file" \
  "$MEMORY_SAMPLE_INTERVAL_SECONDS" "$cgroup_dir" &
monitor_pid=$!
sleep 0.2
printf 'running\n' > "$phase_file"
touch "$raw_dir/.run-replay"
set +e
wait "$client_pid"
client_status=$?
set -e
client_pid=''
printf 'done\n' > "$phase_file"
kill "$monitor_pid" 2>/dev/null || true
wait "$monitor_pid" 2>/dev/null || true
monitor_pid=''

test -s "$raw_dir/replay/steps.tsv"
test "$(($(wc -l < "$raw_dir/replay/steps.tsv") - 1))" = 26
grep -q 'root=/dev/pmem0' "$raw_dir/replay/proc-cmdline.txt"
grep -q 'rootflags=dax=always' "$raw_dir/replay/proc-cmdline.txt"
grep -q '/dev/pmem0' "$raw_dir/replay/findmnt.txt"
oracle_status=0
{
  grep -F '    document.addEventListener("DOMContentLoaded", () => {' "$raw_dir/replay/stdout/024.log" || oracle_status=1
  grep -F '      const node = document.getElementById("lastStroke");' "$raw_dir/replay/stdout/024.log" || oracle_status=1
} > "$raw_dir/oracle-matches.txt"
printf '%s\n' "$oracle_status" > "$raw_dir/oracle-exit-code.txt"
printf '%s\n' "$run_id" > "$output_root/latest-run.txt"
python "$script_dir/analyze.py" "$output_root" \
  "$repo_root/motivation/results/exp1-single-app-smoke/agentenv"
echo "raw result: $raw_dir"
echo "summary:    $output_root/summary.md"
((client_status == 0)) || exit "$client_status"
exit "$oracle_status"
