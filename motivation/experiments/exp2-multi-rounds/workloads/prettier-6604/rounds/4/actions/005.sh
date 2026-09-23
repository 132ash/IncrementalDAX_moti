#!/usr/bin/env bash
printf '%s\n' 'type I = Array<((A | B))[K]>' 'type J = readonly ((A | B))[K][]' | node ./bin/prettier.js --parser typescript
