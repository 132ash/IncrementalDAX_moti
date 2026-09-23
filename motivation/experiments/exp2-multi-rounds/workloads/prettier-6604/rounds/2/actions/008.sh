#!/usr/bin/env bash
printf '%s\n' 'type C = 0 extends ((1 extends 2 ? 3 : 4)) ? 5 : 6' 'type D = ((0 extends 1 ? 2 : 3)) extends 4 ? 5 : 6' | node ./bin/prettier.js --parser typescript
