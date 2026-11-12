# ADR-002: Simulation Reproducibility and Randomness Control

Status: Accepted

## Decision

All stochastic simulation modules must use explicit,
documented random seeds.

Random-number generation must remain deterministic
for identical code, configuration, seed values,
scenario ordering, and software environment.

## Current implementation

- Monte Carlo validation uses BASE_SEED = 20261030.
- Robustness testing uses RANDOM_SEED = 2026,
  with scenario-specific seed offsets.
- OCV-SOC fusion uses a module-level generator
  initialized with seed 20261030.
- SOC estimation uses a module-level generator
  initialized with seed 20261030.
- SOH estimation uses a module-level generator
  initialized with seed 20261031.
- RUL estimation uses a module-level generator
  initialized with seed 20261032.
- Temperature sensor fault simulation initializes
  its generator with seed 42 for each function call.

## Reproducibility verification

Two consecutive executions of the regression suite
produced identical SHA-256 hashes for all files
in results/metrics.

Regression results:
- Passed stages: 10
- Failed stages: 0
- Errors: 0
- Timeouts: 0
- Missing stages: 0
- Blocked stages: 0

## Limitations

Reproducibility has been verified across fresh
executions in the current environment.

The regression harness also repeats the seeded robustness/disturbance
simulation twice and compares SHA-256 hashes for its CSV and JSON outputs.
`results/regression/reproducibility_report.json` records the seed, Python and
NumPy versions, model source hash, output hashes, and comparison result. This
is a focused SIM-012 check for that experiment; it does not establish
reproducibility for every simulation or across environments.

For each regression stage, the suite records the entrypoint source hash,
Python version, bounded literal configuration constants, seed constants, and
hashes for metrics/figures modified by that run in `regression_report.json`.
This is an execution manifest for registered stages. Runtime-built settings
and simulations not registered in the suite still require explicit coverage.

Cross-platform reproducibility and reproducibility
across different Python or dependency versions
have not yet been established.

## Future work

- Document seed ownership for every stochastic module.
- Preserve intentional scenario ordering.
- Record Python and dependency versions.
- Re-run reproducibility checks after changes to
  stochastic models or simulation configuration.
