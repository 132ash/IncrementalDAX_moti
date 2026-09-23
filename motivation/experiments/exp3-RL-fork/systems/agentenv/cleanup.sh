#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
experiment_root="${MIXFS_EXPERIMENT_ROOT:-$(cd -- "$script_dir/../.." && pwd)}"
repo_root="$(cd -- "$experiment_root/../../.." && pwd)"
output_root="${OUTPUT_ROOT:-$repo_root/motivation/results/exp5-RL-fork}"
active="$(aenv list)"
while IFS= read -r -d '' record; do
  tail -n +2 "$record" | cut -f2 | while read -r id; do
    jq -e --arg id "$id" '.[] | select((.sandboxID // .sandbox_id // .id) == $id)' <<< "$active" >/dev/null && aenv delete "$id" || true
  done
done < <(find "$output_root" -type f -name sandbox-ids.tsv -print0)
