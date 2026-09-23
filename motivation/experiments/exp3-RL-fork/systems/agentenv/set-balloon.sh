#!/usr/bin/env bash
set -euo pipefail
mode=${1:?usage: set-balloon.sh on|off}
case "$mode" in
  on) value=true ;;
  off) value=false ;;
  *) echo 'mode must be on or off' >&2; exit 2 ;;
esac
test "$(aenv list | jq 'length')" = 0
docker exec aenv-server sed -i \
  -e '/^free_page_reporting = /d' \
  -e "/^\[firecracker\]/a free_page_reporting = $value" \
  /workspace/config/default.toml
docker restart aenv-server >/dev/null
for i in {1..30}; do
  if aenv list >/dev/null 2>&1; then
    echo "AgentENV free_page_reporting=$value"
    exit 0
  fi
  sleep 1
done
echo 'AgentENV server did not become ready' >&2
exit 1
