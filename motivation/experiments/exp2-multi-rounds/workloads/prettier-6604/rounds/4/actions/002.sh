#!/usr/bin/env bash
grep -RIn 'typescript' tests_config tests_integration scripts | sed -n '1,180p'
