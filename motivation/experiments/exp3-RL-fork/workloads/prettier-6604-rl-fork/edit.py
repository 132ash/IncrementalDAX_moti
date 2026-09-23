#!/usr/bin/env python3
"""Deterministic candidate edit and regression input for the Prettier task."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path("/testbed")
PRINTER = ROOT / "src/language-js/printer-estree.js"
OLD = '''    case "TSIndexedAccessType":
      return concat([
        path.call(print, "objectType"),
        "[",
        path.call(print, "indexType"),
        "]"
      ]);'''

CASES = {
    "backbone": ("backbone", "type T = ((A | B))[K]"),
    "early_1": ("union", "type T = ((A | B))[K]"),
    "early_2": ("conditional", "type T = ((A extends B ? C : D))[K]"),
    "early_3": ("operator", "type T = ((keyof A))[K]"),
    "late_1": ("intersection", "type T = ((A & B))[K]"),
    "late_2": ("nested", "type T = Array<((A | B))[K]>"),
    "late_3": ("keyof", "type T = ((keyof A))[K]"),
}


def main() -> None:
    mode = sys.argv[1]
    if mode == "core" or mode.startswith("early_"):
        source = PRINTER.read_text(encoding="utf-8")
        if mode == "core" or mode == "early_3":
            types = ("TSUnionType", "TSIntersectionType", "TSConditionalType", "TSTypeOperator")
        elif mode == "early_1":
            types = ("TSUnionType", "TSIntersectionType")
        else:
            types = ("TSConditionalType", "TSTypeOperator")
        condition = " ||\n          ".join(f'unwrapped.type === "{kind}"' for kind in types)
        new = '''    case "TSIndexedAccessType": {
      const objectDoc = path.call(print, "objectType");
      let unwrapped = n.objectType;
      while (unwrapped && unwrapped.type === "TSParenthesizedType") {
        unwrapped = unwrapped.typeAnnotation;
      }
      const needsParens =
        unwrapped &&
        (''' + condition + ''');
      return concat([
        needsParens ? concat(["(", objectDoc, ")"]) : objectDoc,
        "[",
        path.call(print, "indexType"),
        "]"
      ]);
    }'''
        if OLD not in source:
            raise SystemExit("expected original printer block absent")
        PRINTER.write_text(source.replace(OLD, new, 1), encoding="utf-8")
    if mode in CASES:
        name, contents = CASES[mode]
        path = ROOT / "tests" / f"mixfs-exp5-{name}.ts"
        path.write_text(contents + "\n", encoding="utf-8")
        print(path.relative_to(ROOT))
    elif mode != "core":
        raise SystemExit(f"unknown edit mode: {mode}")


if __name__ == "__main__":
    main()
