#!/usr/bin/env bash
# Public experiment entry point.  Runtime-specific scripts stay below the
# experiment directory and are intentionally selected only through this map.
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'EOF'
usage: bash motivation/experiments/run.sh <system> <workload> [action] [args...]

Available combinations:
  agentenv prettier-14400 [run|cleanup|enable-direct-io|disable-direct-io]
  trenvx   prettier-14400 [run|setup|build-kernel]
  agentenv-page-cache prettier-6604 [run|cleanup]
  agentenv-drop-cache prettier-6604 [run|cleanup]
  trenvx               prettier-6604 [run|setup|build-kernel]
  agentenv-page-cache prettier-6604-fork [run|cleanup]
  agentenv-drop-cache prettier-6604-fork [run|cleanup]
  trenvx               prettier-6604-fork [run|setup|build-kernel]
  agentenv prettier-6604-realistic-fork [run|cleanup]
  trenvx   prettier-6604-realistic-fork [run|setup|build-kernel]
  agentenv prettier-6604-rl-fork [grpo|bpo|tvcache|cleanup]
  trenvx   prettier-6604-rl-fork [grpo|bpo|tvcache|setup|build-kernel]

`run` is the default action.  Examples:
  bash motivation/experiments/run.sh agentenv prettier-14400
  bash motivation/experiments/run.sh trenvx prettier-14400 setup
  RUN_ID=trial-02 bash motivation/experiments/run.sh trenvx prettier-14400
EOF
}

if [[ ${1:-} == --help || ${1:-} == -h ]]; then
  usage
  exit 0
fi
if [[ $# -lt 2 ]]; then
  usage >&2
  exit 2
fi

system=$1
workload=$2
action=${3:-run}
if [[ $# -ge 3 ]]; then
  shift 3
else
  shift 2
fi

case "$system:$workload:$action" in
  agentenv:prettier-14400:run|agentenv:prettier-14400:cleanup|agentenv:prettier-14400:enable-direct-io|agentenv:prettier-14400:disable-direct-io)
    experiment_root="$script_dir/exp1-single-app-smoke"
    target="$experiment_root/systems/agentenv/$action.sh"
    ;;
  trenvx:prettier-14400:run|trenvx:prettier-14400:setup|trenvx:prettier-14400:build-kernel)
    experiment_root="$script_dir/exp1-single-app-smoke"
    target="$experiment_root/systems/trenvx/$action.sh"
    ;;
  agentenv-page-cache:prettier-6604:run|agentenv-page-cache:prettier-6604:cleanup)
    experiment_root="$script_dir/exp2-multi-rounds"
    target="$experiment_root/systems/agentenv/$action.sh"
    export AGENTENV_CACHE_MODE=preserve
    ;;
  agentenv-drop-cache:prettier-6604:run|agentenv-drop-cache:prettier-6604:cleanup)
    experiment_root="$script_dir/exp2-multi-rounds"
    target="$experiment_root/systems/agentenv/$action.sh"
    export AGENTENV_CACHE_MODE=drop
    ;;
  trenvx:prettier-6604:run|trenvx:prettier-6604:setup|trenvx:prettier-6604:build-kernel)
    experiment_root="$script_dir/exp2-multi-rounds"
    target="$experiment_root/systems/trenvx/$action.sh"
    ;;
  agentenv-page-cache:prettier-6604-fork:run|agentenv-page-cache:prettier-6604-fork:cleanup)
    experiment_root="$script_dir/exp3-fork"
    target="$experiment_root/systems/agentenv/$action.sh"
    export AGENTENV_CACHE_MODE=preserve
    ;;
  agentenv-drop-cache:prettier-6604-fork:run|agentenv-drop-cache:prettier-6604-fork:cleanup)
    experiment_root="$script_dir/exp3-fork"
    target="$experiment_root/systems/agentenv/$action.sh"
    export AGENTENV_CACHE_MODE=drop
    ;;
  trenvx:prettier-6604-fork:run|trenvx:prettier-6604-fork:setup|trenvx:prettier-6604-fork:build-kernel)
    experiment_root="$script_dir/exp3-fork"
    target="$experiment_root/systems/trenvx/$action.sh"
    ;;
  agentenv:prettier-6604-realistic-fork:run|agentenv:prettier-6604-realistic-fork:cleanup)
    experiment_root="$script_dir/exp4-realistic-fork"
    target="$experiment_root/systems/agentenv/$action.sh"
    ;;
  trenvx:prettier-6604-realistic-fork:run|trenvx:prettier-6604-realistic-fork:setup|trenvx:prettier-6604-realistic-fork:build-kernel)
    experiment_root="$script_dir/exp4-realistic-fork"
    target="$experiment_root/systems/trenvx/$action.sh"
    ;;
  agentenv:prettier-6604-rl-fork:grpo|agentenv:prettier-6604-rl-fork:bpo|agentenv:prettier-6604-rl-fork:tvcache)
    experiment_root="$script_dir/exp5-RL-fork"
    target="$experiment_root/systems/agentenv/run.sh"
    set -- "$action" "$@"
    ;;
  agentenv:prettier-6604-rl-fork:cleanup)
    experiment_root="$script_dir/exp5-RL-fork"
    target="$experiment_root/systems/agentenv/cleanup.sh"
    ;;
  trenvx:prettier-6604-rl-fork:grpo|trenvx:prettier-6604-rl-fork:bpo|trenvx:prettier-6604-rl-fork:tvcache)
    experiment_root="$script_dir/exp5-RL-fork"
    target="$experiment_root/systems/trenvx/run.sh"
    set -- "$action" "$@"
    ;;
  trenvx:prettier-6604-rl-fork:setup|trenvx:prettier-6604-rl-fork:build-kernel)
    experiment_root="$script_dir/exp5-RL-fork"
    target="$experiment_root/systems/trenvx/$action.sh"
    ;;
  *)
    echo "unsupported system/workload/action: $system/$workload/$action" >&2
    usage >&2
    exit 2
    ;;
esac

[[ -x $target ]] || { echo "private script is not executable: $target" >&2; exit 1; }
exec env MIXFS_EXPERIMENT_ROOT="$experiment_root" MIXFS_WORKLOAD_NAME="$workload" "$target" "$@"
