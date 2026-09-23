#!/usr/bin/env bash
find tests -path '*typescript*' -type f -printf '%p\n' | sort | sed -n '1,160p'
