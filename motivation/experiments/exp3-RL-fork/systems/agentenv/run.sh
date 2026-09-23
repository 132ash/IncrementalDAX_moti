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
balloon_mode=${BALLOON_MODE:-on}
[[ $balloon_mode == on || $balloon_mode == off ]] || { echo 'BALLOON_MODE must be on or off' >&2; exit 2; }
output_root="${OUTPUT_ROOT:-$repo/motivation/results/exp5-RL-fork/agentenv/$scenario}"
run_id="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)-$scenario-agentenv}"
raw="$output_root/raw/$run_id"
mkdir -p "$output_root/raw"
exec 9> "$output_root/.run.lock"
flock -n 9
[[ ! -e $raw ]] || { echo "run exists: $raw" >&2; exit 1; }
for cmd in aenv docker jq python3 sudo; do command -v "$cmd" >/dev/null; done
sudo -n true
test "$(aenv list | jq 'length')" = 0
config_mode="$(docker exec aenv-server sh -c "sed -n 's/^free_page_reporting = \(true\|false\)/\1/p' /workspace/config/default.toml" | head -1)"
[[ $config_mode == $(if [[ $balloon_mode == on ]]; then echo true; else echo false; fi) ]] || {
  echo "AgentENV container balloon mode is $config_mode, requested $balloon_mode" >&2; exit 1;
}
export WORKLOAD_NAME WORKLOAD_IMAGE
python3 "$root/workloads/$WORKLOAD_NAME/plan.py"
container_pid="$(docker inspect aenv-server --format '{{.State.Pid}}')"
cgroup_rel="$(awk -F: '$1 == "0" { print $3 }' "/proc/$container_pid/cgroup")"
[[ -n $cgroup_rel && $cgroup_rel != / ]] || { echo 'broad cgroup refused' >&2; exit 1; }
cgroup="/sys/fs/cgroup$cgroup_rel"
mkdir -p "$raw/host"
find "$cgroup" -name cgroup.procs -type f -exec cat {} + 2>/dev/null | sort -u | while read -r pid; do
  [[ $(cat "/proc/$pid/comm" 2>/dev/null || true) == firecracker ]] && printf '%s\n' "$pid"
done > "$raw/host/preexisting-vmm-pids.txt"
while read -r pid; do
  rss="$(awk '$1 == "VmRSS:" { print $2; exit }' "/proc/$pid/status" 2>/dev/null || echo 0)"
  ((rss < 32768)) || { echo "preexisting active Firecracker PID $pid has $rss KiB RSS" >&2; exit 1; }
done < "$raw/host/preexisting-vmm-pids.txt"
printf 'setup\n' > "$raw/.phase"
"$repo/motivation/experiments/lib/host-vmm-memory-monitor.sh" "$raw/host/memory-samples.tsv" "$raw/.phase" 0.1 "$cgroup" firecracker &
monitor=$!
sudo -n stdbuf -oL bpftrace -q "$root/host-kvm-slots.bt" > "$raw/host/kvm-slots.tsv" 2> "$raw/host/kvm-slots.stderr.log" &
slotmon=$!
trap 'kill "$monitor" "$slotmon" 2>/dev/null || true; wait "$monitor" "$slotmon" 2>/dev/null || true' EXIT
sleep 1
kill -0 "$slotmon"
AGENTENV_BALLOON_MODE="$balloon_mode" python3 "$root/controller.py" --system agentenv --scenario "$scenario" --raw-dir "$raw" --cgroup "$cgroup"
kill "$monitor" "$slotmon" 2>/dev/null || true
wait "$monitor" "$slotmon" 2>/dev/null || true
python3 "$root/analyze.py" "$raw"
printf '%s\n' "$run_id" > "$output_root/latest-run.txt"
echo "$output_root/summary.md"
