#!/usr/bin/env bash
node <<'NODE'
const prettier = require("/testbed");
const input = `<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240" viewBox="0 0 24 24"><script>document.addEventListener("DOMContentLoaded", () => { const node = document.getElementById("lastStroke"); if (node) { let svg = node.parentNode.parentNode.parentNode; if ("pauseAnimations" in svg) { let hover = false; let loaded = false; node.addEventListener("endEvent", () => { loaded = true; if (!hover) { svg.pauseAnimations(); } }); svg.addEventListener("mouseenter", () => { hover = true; svg.unpauseAnimations(); }); svg.addEventListener("mouseleave", () => { hover = false; if (loaded) { svg.pauseAnimations(); } }); } } });</script></svg>`;
(async () => console.log(await prettier.format(input, { parser: "html" })))();
NODE
