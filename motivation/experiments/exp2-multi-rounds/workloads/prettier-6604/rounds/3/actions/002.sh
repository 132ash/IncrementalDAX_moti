#!/usr/bin/env bash
grep -RIn 'TSUnionType\|TSIntersectionType\|TSTypeOperator' src/language-js | sed -n '1,200p'
