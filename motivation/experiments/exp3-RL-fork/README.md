# Exp5: agent-sampled code repair across three tasks

This experiment uses the existing pinned Prettier 1.18.2 task plus two
SWE-bench Verified tasks whose expert difficulty label is `>4 hours`:
`pydata__xarray-6992` (Dataset/index invariant repair) and
`sphinx-doc__sphinx-7590` (C++ user-defined-literal parsing). DeepSeek calls
shell tools against an isolated copy of each pinned image. It samples one
adaptive backbone, saves an early state after investigation and a later state
after the first candidate fix, then samples three continuations from each.
Commands, exits, outputs, and API messages are frozen in each workload's
`agent-sampling.json`; the API key is never saved.

This is a sampled code-repair agent trace, not a trained RL policy. The
experimenter fixes the two checkpoint positions and the edge-case goal of each
branch; the model chooses individual shell actions after seeing tool output.
The tested schedules are GRPO (seven independent paths), BPO (one backbone
plus six children from two saved states), and TVCache (the rollout prefix
trie). Every schedule represents the same 35 logical segments. GRPO executes
all 35 physically; BPO executes 17; TVCache executes 13 for Prettier and 17
for Xarray/Sphinx because only the Prettier branches share an additional
post-checkpoint inspect segment. Agents use source inspection, minimal
reproducers, edits, and focused tests, never dependency installation or a full
test suite. Failed investigative calls remain part of the frozen trace.
`plan.py` validates the manifests without regenerating them.

## Per-task comparison

Set the task-specific variables, then run one AgentENV w/o balloon replay and
one TrEnv-X replay for each desired schedule. For example, for Xarray BPO:

```bash
export WORKLOAD_NAME=xarray-6992-rl-fork
export WORKLOAD_IMAGE='ghcr.io/epoch-research/swe-bench.eval.x86_64.pydata__xarray-6992@sha256:c05101ef7105599eca1b7d15279a2928ac5453876cd2b83008deb9165d752655'
export DERIVED_IMAGE='mixfs/xarray-6992-exp5-trenvx:c05101ef7105'
export TEMPLATE_ID='xarray-6992-exp5-ch'
python3 motivation/experiments/exp5-RL-fork/workloads/$WORKLOAD_NAME/plan.py
bash motivation/experiments/exp5-RL-fork/systems/agentenv/set-balloon.sh off
BALLOON_MODE=off OUTPUT_ROOT="$PWD/motivation/results/exp5-RL-fork/xarray-6992/agentenv-balloon-off/bpo" \
  bash motivation/experiments/exp5-RL-fork/systems/agentenv/run.sh bpo
source /home/shao/miniconda3/etc/profile.d/conda.sh
conda activate hybridfs
bash motivation/experiments/exp5-RL-fork/systems/trenvx/setup.sh
OUTPUT_ROOT="$PWD/motivation/results/exp5-RL-fork/xarray-6992/trenvx/bpo" \
  bash motivation/experiments/exp5-RL-fork/systems/trenvx/run.sh bpo
python3 motivation/experiments/exp5-RL-fork/compare.py xarray-6992-rl-fork bpo \
  motivation/results/exp5-RL-fork/xarray-6992
```

AgentENV receives the workload directory at cold start. TrEnv-X bakes the same
workload into its task-specific base template. Guest resources stay fixed at
two vCPUs and 4096 MiB.

At a TrEnv-X checkpoint, the controller runs `sync; echo 3 > drop_caches`,
archives the parent's overlay upper with whiteouts, ownership, ACLs, and
xattrs intact, and seals it as a new immutable ext4 DAX layer. A clean staging
VM is snapshotted with the inherited layer chain ordered newest-to-oldest over
the immutable base rootfs. The continuing parent branch and all children then
restore from that template with fresh independent writable uppers. Every
instance hard-links the same base and checkpoint-layer inodes, so historical
file reads share one host file-cache/DAX backing. Because `/tmp` is a separate
tmpfs rather than part of the root upper, it is captured and restored
separately to preserve the frozen trace; it is not counted as a DAX layer.
AgentENV uses its persistent snapshot and native filesystem CoW with balloon
disabled.

The tool timer wraps each guest action only. It excludes model requests,
checkpoint and DAX layer/template construction, sandbox startup,
uploads/downloads, and
measurement. The host monitor samples aggregate VMM PSS at a 0.1-second target
interval. After each segment and at terminal retention, a guest file-LRU probe
maps pages to host PFNs, deduplicates them, and adds read-only DAX mapping PSS.
This file-content measure can miss spikes between segment boundaries. VMM PSS
includes resident guest RAM and mapped files but excludes daemon, kernel, and
unmapped host block cache. The two memory measures overlap and must not be added.

The current result set contains all three tasks under BPO, GRPO, and TVCache.
Successful controllers delete all sandboxes and checkpoint templates in
`finally`.
