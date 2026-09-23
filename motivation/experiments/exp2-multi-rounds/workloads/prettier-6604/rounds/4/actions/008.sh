#!/usr/bin/env bash
git diff --stat && git diff -- src/language-js/printer-estree.js | sed -n '1,240p'
