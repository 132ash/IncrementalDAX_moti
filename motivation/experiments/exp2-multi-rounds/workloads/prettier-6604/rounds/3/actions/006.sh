#!/usr/bin/env bash
grep -RIn 'type T[1-4]' tests tests_config 2>/dev/null | sed -n '1,120p'
