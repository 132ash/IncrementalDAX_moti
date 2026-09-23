#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
experiment_root="${MIXFS_EXPERIMENT_ROOT:-$(cd -- "$script_dir/../.." && pwd)}"
repo_root="$(cd -- "$experiment_root/../../.." && pwd)"
source "$script_dir/config.env"
[[ ${CONDA_DEFAULT_ENV:-} == hybridfs ]] || { echo 'activate hybridfs first' >&2; exit 1; }
for tool in flock python sha256sum sudo; do command -v "$tool" >/dev/null || { echo "missing command: $tool" >&2; exit 1; }; done
sudo -n true
test -s "$DATA_ROOT/templates/$TEMPLATE_ID/image/rootfs.ext4"
host_pmem_rootfs_bytes="$(stat -c %s "$DATA_ROOT/templates/$TEMPLATE_ID/image/rootfs.ext4")"

output_root="${OUTPUT_ROOT:-$repo_root/$OUTPUT_REL}"
run_id="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)-trenvx}"
raw_dir="$output_root/raw/$run_id"
lock_file="$output_root/.run.lock"
backend_pid=''
mkdir -p "$output_root/raw" "$output_root/figures"
exec 9> "$lock_file"
flock -n 9 || { echo "another run holds $lock_file" >&2; exit 1; }
[[ ! -e $raw_dir ]] || { echo "run directory exists: $raw_dir" >&2; exit 1; }
mkdir -p "$raw_dir"
cleanup() { if [[ -n $backend_pid ]]; then kill "$backend_pid" 2>/dev/null || true; wait "$backend_pid" 2>/dev/null || true; fi; }
trap cleanup EXIT INT TERM

"$experiment_root/workloads/$WORKLOAD_NAME/build-manifests.sh"
{
  printf 'run_id=%s\nsystem=trenvx\ncache_mode=drop\nworkload_image=%s\ntemplate_id=%s\n' "$run_id" "$WORKLOAD_IMAGE" "$TEMPLATE_ID"
  printf 'sandbox_cpu=%s\nsandbox_memory_mib=%s\nstarted_utc=%s\n' "$SANDBOX_CPU" "$SANDBOX_MEMORY_MIB" "$(date -u --iso-8601=seconds)"
  printf 'rounds_sha256=%s\n' "$(find "$experiment_root/workloads/$WORKLOAD_NAME/rounds" -name actions.tsv -print0 | sort -z | xargs -0 sha256sum | sha256sum | awk '{print $1}')"
  printf 'latency_scope=actions_only\ntransition_latency_included=false\nfilesystem_restore=rebuild-template-from-latest-writable-rootfs\n'
  printf 'host_pmem_metric=virtio-pmem-read-only-rootfs-mapping-capacity\nhost_pmem_rootfs_bytes=%s\n' "$host_pmem_rootfs_bytes"
} > "$raw_dir/metadata.env"

"$script_dir/start-backend.sh" > "$raw_dir/orchestrator.stdout.log" 2> "$raw_dir/orchestrator.stderr.log" &
backend_pid=$!
for _ in $(seq 1 100); do
  (exec 8<>/dev/tcp/127.0.0.1/$ORCHESTRATOR_PORT) 2>/dev/null && { exec 8>&-; break; }
  kill -0 "$backend_pid" 2>/dev/null || { echo 'orchestrator exited during startup' >&2; exit 1; }
  sleep 0.1
done
(exec 8<>/dev/tcp/127.0.0.1/$ORCHESTRATOR_PORT) 2>/dev/null
exec 8>&-

export ACTION_TIMEOUT_SECONDS MEMORY_SAMPLE_INTERVAL_SECONDS ORCHESTRATOR_PORT
python "$script_dir/client.py" --template "$TEMPLATE_ID" --data-root "$DATA_ROOT" --raw-dir "$raw_dir" --timeout 3600 > "$raw_dir/client.stdout.log" 2> "$raw_dir/client.stderr.log"
for round in 1 2 3 4; do test -s "$raw_dir/rounds/$round/steps.tsv"; done
oracle_status=0
grep -F 'type G = (A & B)[keyof C];' "$raw_dir/rounds/4/stdout/004.log" > "$raw_dir/oracle-matches.txt" || oracle_status=1
printf '%s\n' "$oracle_status" > "$raw_dir/oracle-exit-code.txt"
printf '%s\n' "$run_id" > "$output_root/latest-run.txt"
python "$experiment_root/analyze.py" "$output_root"
echo "raw result: $raw_dir"
echo "summary:    $output_root/summary.md"
exit "$oracle_status"
