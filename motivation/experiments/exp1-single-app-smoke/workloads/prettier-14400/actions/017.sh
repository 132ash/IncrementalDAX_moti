#!/usr/bin/env bash
sed -i '/node\.fullName === "style" \|\|/a\      node.fullName === "svg:script" ||' /testbed/src/language-html/utils/index.js
