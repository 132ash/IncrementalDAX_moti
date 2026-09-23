#!/usr/bin/env bash
find tests_config tests_integration -type f -printf '%p\n' 2>/dev/null | sort | sed -n '1,180p'
