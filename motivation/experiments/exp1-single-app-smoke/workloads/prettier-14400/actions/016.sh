#!/usr/bin/env bash
applypatch <<'PATCH'
*** Begin Patch
*** Update File: /testbed/src/language-html/utils/index.js
@@
-      node.fullName === "svg:style" ||
+      node.fullName === "svg:script" ||
+      node.fullName === "svg:style" ||
*** End Patch
PATCH
