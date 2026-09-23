#!/usr/bin/env bash
rg -n "inferElementParser|isScriptLikeTag|svg:script" /testbed/src/language-html -n && nl -ba /testbed/src/language-html/utils/index.js | sed -n '90,450p'
