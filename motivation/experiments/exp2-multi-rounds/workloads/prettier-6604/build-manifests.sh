#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
for round in 1 2 3 4; do
  manifest="$root/rounds/$round/actions.tsv"
  printf 'step\tsha256\tcommand\n' > "$manifest"
  for action in "$root/rounds/$round/actions"/*.sh; do
    step="$(basename "$action" .sh)"
    command="$(sed -n '2p' "$action" | cut -c1-120)"
    printf '%s\t%s\t%s\n' "$step" "$(sha256sum "$action" | awk '{print $1}')" "$command" >> "$manifest"
  done
done
