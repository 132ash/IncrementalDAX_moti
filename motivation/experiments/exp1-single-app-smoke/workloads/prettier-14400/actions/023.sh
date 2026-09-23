#!/usr/bin/env bash
node -e 'const prettier=require("/testbed"); const input = `<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240" viewBox="0 0 24 24"><script>document.addEventListener("DOMContentLoaded",()=>{const node=document.getElementById("lastStroke");});</script></svg>`; console.log(prettier.format(input,{parser:"html"}))'
