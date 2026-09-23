#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
manifest="$root/actions.tsv"
: > "$manifest"
for action in "$root"/actions/*.sh; do
  step="$(basename "$action" .sh)"
  digest="$(sha256sum "$action" | awk '{print $1}')"
  command="$(sed -n '2p' "$action")"
  printf '%s\t%s\t%s\n' "$step" "$digest" "$command" >> "$manifest"
done
