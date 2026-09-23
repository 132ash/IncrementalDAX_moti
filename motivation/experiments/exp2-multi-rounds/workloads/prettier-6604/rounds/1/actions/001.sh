#!/usr/bin/env bash
find . -maxdepth 2 -type f -not -path './.git/*' | sort | sed -n '1,160p'
