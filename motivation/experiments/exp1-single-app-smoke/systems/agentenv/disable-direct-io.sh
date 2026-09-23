#!/usr/bin/env bash
set -euo pipefail

container=${AENV_CONTAINER_NAME:-aenv-server}
real=/usr/local/bin/uvm-ublk-daemon.buffered
active=/usr/local/bin/uvm-ublk-daemon

test "$(aenv list | jq 'length')" = 0 || {
  echo 'active sandboxes exist; refusing to restart AgentENV' >&2
  exit 1
}
docker exec "$container" test -x "$real" || {
  echo 'buffered-I/O daemon backup is absent; nothing safe to restore' >&2
  exit 1
}
docker exec "$container" mv "$real" "$active"
docker restart "$container" >/dev/null
for attempt in $(seq 1 60); do
  curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS http://127.0.0.1:8000/health >/dev/null
actual="$(docker exec "$container" sed -n 's/.*"ioEngine": \([0-9][0-9]*\).*/\1/p' /workspace/env/overlaybd/overlaybd-global.json)"
test "$actual" = 0 || { echo "buffered I/O verification failed: ioEngine=$actual" >&2; exit 1; }
echo 'Buffered I/O restored and verified: overlaybd ioEngine=0'
