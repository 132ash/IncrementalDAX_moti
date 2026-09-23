#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
experiment_root="${MIXFS_EXPERIMENT_ROOT:-$(cd -- "$script_dir/../.." && pwd)}"
repo_root="$(cd -- "$experiment_root/../../.." && pwd)"
# shellcheck source=config.env
source "$script_dir/config.env"
output_root="${OUTPUT_ROOT:-$repo_root/$OUTPUT_REL}"

shopt -s nullglob
records=("$output_root"/raw/*/sandbox-id.txt)
if ((${#records[@]} == 0)); then
  echo "no recorded sandboxes under $output_root/raw"
  exit 0
fi

active_json="$(aenv list)"
for record in "${records[@]}"; do
  sandbox_id="$(tr -d '[:space:]' < "$record")"
  [[ $sandbox_id =~ ^[0-9a-fA-F-]{36}$ ]] || {
    echo "skip invalid sandbox id in $record" >&2
    continue
  }
  if jq -e --arg id "$sandbox_id" '.[] | select((.sandboxID // .sandbox_id // .id) == $id)' \
    <<< "$active_json" >/dev/null; then
    aenv delete "$sandbox_id"
    printf 'deleted=%s\n' "$sandbox_id" >> "$(dirname "$record")/cleanup.log"
  else
    echo "already absent: $sandbox_id"
  fi
done
