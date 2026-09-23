#!/usr/bin/env bash
grep -RIn 'TSParenthesized\|ConditionalType' src/language-js | sed -n '1,180p'
