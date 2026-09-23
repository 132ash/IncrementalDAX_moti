#!/usr/bin/env bash
node node_modules/.bin/jest --runInBand --listTests --testPathPattern='language-js.*typescript' | sed -n '1,120p'
