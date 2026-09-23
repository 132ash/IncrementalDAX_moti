#!/usr/bin/env bash
python3 - <<'PY'
from pathlib import Path
p = Path('src/language-js/printer-estree.js')
s = p.read_text()
old = '''    case "TSIndexedAccessType":
      return concat([
        path.call(print, "objectType"),
        "[",
        path.call(print, "indexType"),
        "]"
      ]);'''
new = '''    case "TSIndexedAccessType": {
      const objectType = n.objectType;
      const objectDoc = path.call(print, "objectType");
      let unwrapped = objectType;
      while (unwrapped && unwrapped.type === "TSParenthesizedType") {
        unwrapped = unwrapped.typeAnnotation;
      }
      const needsParens =
        unwrapped &&
        (unwrapped.type === "TSUnionType" ||
          unwrapped.type === "TSIntersectionType" ||
          unwrapped.type === "TSConditionalType" ||
          unwrapped.type === "TSTypeOperator");
      return concat([
        needsParens ? concat(["(", objectDoc, ")"]) : objectDoc,
        "[",
        path.call(print, "indexType"),
        "]"
      ]);
    }'''
if new not in s:
    if old not in s:
        raise SystemExit('expected TSIndexedAccessType block not found')
    p.write_text(s.replace(old, new, 1))
PY
