#!/usr/bin/env bash
git -C /testbed checkout -- src/language-html/utils/index.js && sed -i 's/node\.fullName === "svg:style" \|\|/node.fullName === "svg:script" ||\n      node.fullName === "svg:style" ||/' /testbed/src/language-html/utils/index.js && nl -ba /testbed/src/language-html/utils/index.js | sed -n '100,140p'
