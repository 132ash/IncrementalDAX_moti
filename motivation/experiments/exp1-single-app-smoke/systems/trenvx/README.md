# Prettier #14400 on TrEnv-X

This baseline replays the shared 26-action workload on TrEnv-X's high-density
path: the pinned custom Cloud Hypervisor, a shared read-only ext4 image exposed
as `virtio-pmem` with DAX, and a private writable virtio-blk overlay.

```bash
conda activate hybridfs
bash motivation/experiments/run.sh trenvx prettier-14400 setup
bash motivation/experiments/run.sh trenvx prettier-14400
```

`setup.sh` builds the derived workload image, pinned Cloud Hypervisor, missing
CH guest kernel (through `build-kernel.sh`), and TrEnv-X components, then creates
the snapshot template. It refuses to overwrite an existing template; use
`REBUILD_TEMPLATE=1` only when intentionally rebuilding it. `run.sh`
starts an isolated local orchestrator, creates one sandbox, verifies pmem/DAX,
collects raw data, deletes the sandbox, and rebuilds the comparison summary.

Runtime artifacts live under `/var/lib/trenvx`; protocol is co-located with the
workload at `experiments/exp1-single-app-smoke/`, and results are under
`results/exp1-single-app-smoke/trenvx/`. Use the `hybridfs` Conda environment
for both setup and runs.
