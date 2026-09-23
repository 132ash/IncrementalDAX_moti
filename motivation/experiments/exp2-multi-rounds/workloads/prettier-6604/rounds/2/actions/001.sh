#!/usr/bin/env bash
grep -RIn 'TSIndexedAccessType' src/language-js | sed -n '1,180p'
