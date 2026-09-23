#!/usr/bin/env bash
printf '%s\n' 'type A = ((number | string))["toString"]' 'type B = ((keyof A))["foo"]' > /tmp/mixfs-cases-round2.ts
node ./bin/prettier.js --parser typescript /tmp/mixfs-cases-round2.ts
