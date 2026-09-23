#!/usr/bin/env bash
(nl -ba /testbed/src/language-html/utils/index.js | sed -n '1,260p' && echo '---' && nl -ba /testbed/src/language-html/parser-html.js | sed -n '1,220p')
