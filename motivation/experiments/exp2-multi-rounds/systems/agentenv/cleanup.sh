#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
experiment_root="${MIXFS_EXPERIMENT_ROOT:-$(cd -- "$script_dir/../.." && pwd)}"
repo_root="$(cd -- "$experiment_root/../../.." && pwd)"
mode=${AGENTENV_CACHE_MODE:-preserve}
output_root="${OUTPUT_ROOT:-$repo_root/motivation/results/exp2-multi-rounds/agentenv-$mode-cache}"
active="$(aenv list)"
shopt -s nullglob
for record in "$output_root"/raw/*/sandbox-ids.txt; do
  while read -r id; do
    jq -e --arg id "$id" '.[] | select((.sandboxID // .sandbox_id // .id) == $id)' <<< "$active" >/dev/null && aenv delete "$id" || true
  done < "$record"
done
while read -r alias; do aenv template delete "$alias" 2>/dev/null || true; done < <(aenv snapshot list --output json | jq -r '.[] | (.name // .alias // empty) | select(startswith("mixfs-exp2-"))')
