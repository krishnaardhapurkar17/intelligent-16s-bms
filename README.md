# Simulation-First 16S Intelligent BMS

A simulation-first 16-series-cell Intelligent Battery Management System.

## Development Stack
- Python
- PyBaMM
- NumPy / SciPy
- Pandas
- Matplotlib
- Pytest
- KiCad

## Project Scope
- 16S battery modelling
- Cell monitoring
- SOC/SOH/SOP/SOS estimation
- Fault detection and localization
- Active balancing simulation
- AI-based battery diagnostics
- CMU/BMU/PMU/BDU architecture
- Verification and validation

## Project Status
Simulation models, diagnostics, supervisory controls, PMU/IMU/TMU abstractions,
and BDU protection logic are present. Transport-independent message contracts,
simulation command authorization, and lifecycle event logging/replay are also
implemented. See `docs/requirements-traceability-matrix.md` for verified gaps;
the RTM is an engineering worklist, not a certification statement.

The hardware files are a non-release schematic/design study. Grounded USB
service is prohibited while the pack is connected; the active-balancer is
deferred from the build/procurement baseline; external high-voltage switching
components remain unselected; and physical IMD/HVIL, PCB layout and physical
validation are outside the current scope. Do not connect a battery to the
draft design.

Reproducible idealized precharge R-C, software fault-injection, and synthetic dynamic-load SOC
initialization experiments are included. They are software-model evidence,
not KiCad SPICE, component-model, hardware, or vehicle validation. See
`docs/portfolio-evidence-register.md`.

## Supplied AI estimators

Supplied NMC/NMC-LCO model assets are preserved under `models/ai/`. Portable
LFP SOH/RUL forests trained on UConn reference performance tests are also
available through the AI adapter; their whole-cell held-out results and limits
are documented in `models/ai/README.md`. LFP SOC AI remains disabled because
the available data do not support independent cell-held-out validation of a
temperature-aware model. All AI estimates are research-only warnings and must
not replace primary protection logic. See `models/ai/README.md` for feature
contracts and verification evidence.

## Run checks
Create an isolated environment and install the core project dependencies:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r environment/requirements-core.txt
```

For SOC CNN-LSTM inference, also install
`.\.venv\Scripts\python.exe -m pip install -r environment/requirements-ai.txt`.
Run the regression suite with
`.\.venv\Scripts\python.exe tests/regression/run_regression.py`. It writes its
report under `results/regression/`.

Regenerate the focused assumption-only experiments with:

```powershell
.\.venv\Scripts\python.exe tools\run_precharge_assumption_sim.py
.\.venv\Scripts\python.exe tools\run_soc_drive_cycle_experiment.py
.\.venv\Scripts\python.exe tools\run_software_fault_injection_report.py
```

## LFP model data workflow

Keep the downloaded raw files in `datasets/` (they are excluded from Git). Run
`.\.venv\Scripts\python.exe tools/prepare_lfp_dataset.py --all` to build compact
tables under `results/raw/lfp/`, then run
`.\.venv\Scripts\python.exe tools/train_lfp_tree_models.py` to train LFP SOH/RUL
forests and reproduce the whole-cell validation report. Add
`--split protocol-group` to evaluate on unseen aging conditions. See
`models/ai/README.md` for metrics, limits, and the disabled LFP SOC AI path.

For the complete unit suite, run
`.\.venv\Scripts\python.exe -m pytest tests/unit -q`. For statement and
branch coverage, install `environment/requirements-dev.txt`, run
`coverage run --branch --source=software,models -m pytest tests/unit -q`, then
`coverage report -m`. The current result is recorded in
`results/metrics/unit_test_coverage.json`; coverage is not a safety metric.

## Limitations
Simulation and engineering design project.
Not safety certified or production qualified.
