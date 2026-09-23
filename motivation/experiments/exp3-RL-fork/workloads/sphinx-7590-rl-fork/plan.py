#!/usr/bin/env python3
"""Validate one frozen BPO trace before replay."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main() -> None:
    rollouts = json.loads((ROOT / "rollouts.json").read_text())
    expected_roles = {"backbone", "early_1", "early_2", "early_3", "late_1", "late_2", "late_3"}
    if set(rollouts) != expected_roles or len(rollouts["backbone"]) != 5:
        raise SystemExit("invalid BPO rollout graph")
    backbone = rollouts["backbone"]
    for role in sorted(expected_roles - {"backbone"}):
        expected_prefix = backbone[:2] if role.startswith("early") else backbone[:4]
        if rollouts[role][:len(expected_prefix)] != expected_prefix or len(rollouts[role]) != len(expected_prefix) + 2:
            raise SystemExit(f"invalid BPO prefix for {role}")
    for segment in {item for path in rollouts.values() for item in path}:
        path = ROOT / "segments" / segment / "actions.tsv"
        lines = path.read_text().splitlines()
        if not lines or lines[0] != "step\tsha256\tcommand":
            raise SystemExit(f"invalid header: {segment}")
        rows = [line.split("\t", 2) for line in lines[1:]]
        if len(rows) < 2:
            raise SystemExit(f"too few actions: {segment}")
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
