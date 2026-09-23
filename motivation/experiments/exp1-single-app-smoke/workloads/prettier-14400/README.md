# Prettier #14400 replay workload

This directory is shared by the systems in `exp1-single-app-smoke`. `actions/`
contains the 26 shell tool calls replayed in order, and `guest-runner.sh`
collects the per-action latency, guest-memory, vmstat, patch, and stdout/stderr
artifacts used by the TrEnv-X image. AgentENV uses a small private guest-runner
adapter only to change its upload/artifact paths; it replays this same
`actions/` directory and manifest.

The workload assumes the pinned PolyBench image layout (`/testbed`) and keeps
the two tool-not-found actions (`rg` and `applypatch`) from the recorded
trajectory.  They are part of the replay and are therefore not treated as a
runner failure.
