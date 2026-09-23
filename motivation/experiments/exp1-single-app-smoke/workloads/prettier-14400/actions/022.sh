#!/usr/bin/env bash
perl -0777 -pi -e 's/node\.fullName === "style" \|\|(\s*\n\s*)node\.fullName === "svg:style" \|\|/node.fullName === "style" ||$1      node.fullName === "svg:script" ||$1      node.fullName === "svg:style" ||/' /testbed/src/language-html/utils/index.js
nl -ba /testbed/src/language-html/utils/index.js | sed -n '100,140p'
