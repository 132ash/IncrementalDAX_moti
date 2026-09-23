#!/usr/bin/env bash
grep -RIl 'keyof\|TSIndexedAccessType' tests | sort | sed -n '1,120p'
