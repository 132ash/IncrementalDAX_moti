#!/usr/bin/env bash
printf '%s\n' 'type G = ((A & B))[keyof C]' 'type H = ((A extends B ? C : D))[K]' > /tmp/mixfs-cases-round4.ts
node ./bin/prettier.js --parser typescript /tmp/mixfs-cases-round4.ts
