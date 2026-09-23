#!/usr/bin/env python3
"""Validate the frozen, agent-sampled BPO trace before each replay."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ROLLOUTS = {
    "backbone": ["read_repo", "read_typescript", "core_patch", "core_verify", "backbone_finish"],
    **{f"early_{i}": ["read_repo", "read_typescript", "early_inspect", f"early_{i}"] for i in range(1, 4)},
    **{f"late_{i}": ["read_repo", "read_typescript", "core_patch", "core_verify", "late_inspect", f"late_{i}"] for i in range(1, 4)},
}


def main() -> None:
    actual = json.loads((ROOT / "rollouts.json").read_text())
    if actual != ROLLOUTS:
        raise SystemExit("rollout graph differs from the frozen BPO schedule")
    for segment in {item for path in ROLLOUTS.values() for item in path}:
        path = ROOT / "segments" / segment / "actions.tsv"
        lines = path.read_text().splitlines()
        if lines[0] != "step\tsha256\tcommand":
            raise SystemExit(f"invalid header: {segment}")
        rows = [line.split("\t", 2) for line in lines[1:]]
        if not rows:
            raise SystemExit(f"empty segment: {segment}")
        for index, row in enumerate(rows, 1):
            if len(row) != 3:
                raise SystemExit(f"invalid fields: {segment}/{index}")
            step, sha256, command = row
            if step != f"{index:03}" or sha256 != hashlib.sha256(command.encode()).hexdigest():
                raise SystemExit(f"invalid action: {segment}/{index}")
            if "\n" in command or "\t" in command:
                raise SystemExit(f"multiline action: {segment}/{index}")
    print("frozen BPO trace valid")


if __name__ == "__main__":
    main()
