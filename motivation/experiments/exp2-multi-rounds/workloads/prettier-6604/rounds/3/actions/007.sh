#!/usr/bin/env bash
printf '%s\n' 'type E = ((number | string))["toString"]' 'type F = ((keyof E))["foo"]' > /tmp/mixfs-cases-round3.ts
node ./bin/prettier.js --parser typescript /tmp/mixfs-cases-round3.ts
