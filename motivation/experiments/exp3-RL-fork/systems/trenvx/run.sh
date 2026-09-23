#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd -- "$script_dir/../.." && pwd)"
repo="$(cd -- "$root/../../.." && pwd)"
source "$script_dir/config.env"
scenario=${1:?usage: run.sh '<grpo|bpo|tvcache>'}
[[ $scenario == grpo || $scenario == bpo || $scenario == tvcache ]] || {
  echo 'scenario must be grpo, bpo, or tvcache' >&2
  exit 2
}
[[ ${CONDA_DEFAULT_ENV:-} == hybridfs ]] || { echo 'activate hybridfs first' >&2; exit 1; }
output_root="${OUTPUT_ROOT:-$repo/motivation/results/exp5-RL-fork/trenvx/$scenario}"
run_id="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)-$scenario-trenvx}"
raw="$output_root/raw/$run_id"
mkdir -p "$output_root/raw"
exec 9> "$output_root/.run.lock"
flock -n 9
[[ ! -e $raw ]] || { echo "run exists: $raw" >&2; exit 1; }
test -s "$DATA_ROOT/templates/$TEMPLATE_ID/image/rootfs.ext4"
mountpoint -q "$DATA_ROOT"
[[ $(stat -f -c %T "$DATA_ROOT") == btrfs ]]
if pgrep -x cloud-hyperviso >/dev/null; then
  echo 'another Cloud Hypervisor VM is already running; global peak attribution would be ambiguous' >&2
  exit 1
fi
sudo -n true
python3 "$root/workloads/$WORKLOAD_NAME/plan.py"
mkdir -p "$raw/host"
printf 'setup\n' > "$raw/.phase"
"$script_dir/start-backend.sh" > "$raw/orchestrator.stdout.log" 2> "$raw/orchestrator.stderr.log" &
backend=$!
HOST_INCLUDE_ALL_MATCHING_VMM=1 "$repo/motivation/experiments/lib/host-vmm-memory-monitor.sh" "$raw/host/memory-samples.tsv" "$raw/.phase" 0.1 /sys/fs/cgroup/user.slice/trenvx-exp5 'cloud-hyperviso*' &
monitor=$!
sudo -n stdbuf -oL bpftrace -q "$root/host-kvm-slots.bt" > "$raw/host/kvm-slots.tsv" 2> "$raw/host/kvm-slots.stderr.log" &
slotmon=$!
trap 'kill "$monitor" "$slotmon" "$backend" 2>/dev/null || true; wait "$monitor" "$slotmon" "$backend" 2>/dev/null || true' EXIT
sleep 1
kill -0 "$slotmon"
for _ in $(seq 1 100); do
  (exec 8<>/dev/tcp/127.0.0.1/$ORCHESTRATOR_PORT) 2>/dev/null && { exec 8>&-; break; }
  kill -0 "$backend"
  sleep 0.1
done
(exec 8<>/dev/tcp/127.0.0.1/$ORCHESTRATOR_PORT) 2>/dev/null
exec 8>&-
export DATA_ROOT TEMPLATE_ID ORCHESTRATOR_PORT WORKLOAD_IMAGE WORKLOAD_NAME
python "$root/controller.py" --system trenvx --scenario "$scenario" --raw-dir "$raw" --cgroup /sys/fs/cgroup/user.slice/trenvx-exp5
kill "$monitor" "$slotmon" 2>/dev/null || true
wait "$monitor" "$slotmon" 2>/dev/null || true
python3 "$root/analyze.py" "$raw"
printf '%s\n' "$run_id" > "$output_root/latest-run.txt"
echo "$output_root/summary.md"
