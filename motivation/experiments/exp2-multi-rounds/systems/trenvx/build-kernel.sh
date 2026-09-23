#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$script_dir/../../../exp1-single-app-smoke/systems/trenvx/build-kernel.sh" "$@"
