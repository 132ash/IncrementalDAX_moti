#!/usr/bin/env bash
git -C /testbed checkout -- src/language-html/utils/index.js && nl -ba /testbed/src/language-html/utils/index.js | sed -n '90,140p'
