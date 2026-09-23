# Prettier #14400 / TrEnv-X results

- [`summary.md`](summary.md) is the generated TrEnv-X/AgentENV comparison.
- [`analysis.md`](analysis.md) explains the guest-memory breakdown and the
  startup/action latency differences, including comparability limits.
- `raw/20260914T124731Z-trenvx-ch-dax-replay/` is the accepted complete run.
- `diagnostics/` retains incomplete bring-up attempts (port collision, host
  iptables lock ACL, optional proxy routing, guest ownership, and the initial
  action-024 oracle correction).  They are not consumed by the analyzer.

The accepted TrEnv-X and AgentENV runs have the same action manifest digest.
Both are single-run pipeline validations, not a statistically sufficient
performance study.
