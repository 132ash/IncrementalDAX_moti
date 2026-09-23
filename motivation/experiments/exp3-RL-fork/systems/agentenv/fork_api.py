#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tomllib
import urllib.error
import urllib.request
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sandbox_id")
    parser.add_argument("output", type=Path)
    parser.add_argument("--count", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=3600)
    args = parser.parse_args()
    credentials = Path.home() / ".config/aenv/credentials"
    with credentials.open("rb") as handle:
        auth = tomllib.load(handle)
    url = f"{auth['url'].rstrip('/')}/sandboxes/{args.sandbox_id}/fork"
    request = urllib.request.Request(
        url,
        data=json.dumps({"count": args.count, "timeout": args.timeout}).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "X-API-Key": auth["api_key"]},
    )
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        raise SystemExit(f"fork API failed: HTTP {error.code}: {error.read().decode(errors='replace')}") from error
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if len(payload) != args.count:
        raise SystemExit(f"fork API returned {len(payload)} results, expected {args.count}")
    ids = []
    for index, result in enumerate(payload):
        sandbox = result.get("sandbox")
        if not sandbox or not sandbox.get("sandboxID"):
            raise SystemExit(f"fork {index} failed: {result.get('error', result)}")
        ids.append(sandbox["sandboxID"])
    print("\n".join(ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
