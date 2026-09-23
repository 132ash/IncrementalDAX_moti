#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
experiment_root="${MIXFS_EXPERIMENT_ROOT:-$(cd -- "$script_dir/../.." && pwd)}"
repo_root="$(cd -- "$experiment_root/../../.." && pwd)"
exec env ENVIRONMENT=local TRENVX_PRIVATE_UPPER_COPY=1 "$repo_root/baselines/TrEnv-X/packages/orchestrator/bin/orchestrator" --config "$script_dir/config.toml"
