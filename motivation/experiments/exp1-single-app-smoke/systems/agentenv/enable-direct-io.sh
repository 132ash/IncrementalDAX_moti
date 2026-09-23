#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
container=${AENV_CONTAINER_NAME:-aenv-server}
real=/usr/local/bin/uvm-ublk-daemon.buffered
active=/usr/local/bin/uvm-ublk-daemon
staged=/usr/local/bin/uvm-ublk-daemon.direct-wrapper

test "$(aenv list | jq 'length')" = 0 || {
  echo 'active sandboxes exist; refusing to restart AgentENV' >&2
  exit 1
}
test "$(docker inspect "$container" --format '{{.State.Running}}')" = true

if ! docker exec "$container" test -x "$real"; then
  docker exec "$container" mv "$active" "$real"
fi
docker cp "$script_dir/ublk-daemon-direct-io-wrapper.sh" "$container:$staged"
docker exec "$container" chmod 0755 "$staged"
docker exec "$container" mv "$staged" "$active"
docker restart "$container" >/dev/null

for attempt in $(seq 1 60); do
  curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS http://127.0.0.1:8000/health >/dev/null
actual="$(docker exec "$container" sed -n 's/.*"ioEngine": \([0-9][0-9]*\).*/\1/p' /workspace/env/overlaybd/overlaybd-global.json)"
test "$actual" = 2 || { echo "Direct I/O verification failed: ioEngine=$actual" >&2; exit 1; }
echo 'Direct I/O enabled and verified: overlaybd ioEngine=2'
