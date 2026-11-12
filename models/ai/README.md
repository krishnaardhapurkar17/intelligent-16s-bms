# Supplied battery AI model integration

This directory contains runtime-ready assets derived from the user's `AI models/`
folder. The MATLAB SOH and RUL ensembles were exported with
`tools/export_matlab_ensembles.m`; their Python tree walker reproduces MATLAB
predictions for the embedded reference rows to less than 1e-9 absolute error.
The source `.mat` files remain untouched. Runtime inference uses only NumPy and
the JSON exports; MATLAB is needed only to regenerate them.

## Models and input contracts

| Output | Runtime model | Input | Training domain |
|---|---|---|---|
| SOC | `soc_cnn_lstm.keras` | 30 consecutive 10 Hz samples of voltage (V), current (A), and temperature (°C) | LG INR 21700 NMC cells |
| SOH | `soh_ensemble.json` | `cycle`, `Re`, `Rct`, `ambient_temperature`, `capacity_fade`, `delta_Capacity` | NASA NMC/LCO 18650 cells |
| RUL | `rul_ensemble.json` | `cycle`, `SOH`, `Re`, `Rct`, `ambient_temperature`, `capacity_fade`, `delta_Capacity` | NASA NMC/LCO 18650 cells |

Use `software.estimation.ai_battery_estimators.BatteryAIEstimators`. Pass an
explicit `chemistry` to every prediction. The supplied NMC/NMC-LCO assets do
not accept LFP. Separate LFP SOH/RUL forests are documented below. Estimates
are marked `RESEARCH_ONLY`; `AIEstimate.to_message()` emits `WARNING` quality.
These models must not replace the LFP estimators or primary protection path.

SOC normalization ranges and sequence length are held in
`soc_norm_constants.json`; training metrics and split metadata are in
`soc_metadata.json` and `soc_evaluation_results.csv`. The held-out SOC test
cell is NMC069. At 5°C, the supplied evidence reports 2.0014% pooled MAE and a
12.0519% maximum absolute error; this remains a narrow, research dataset.

Install the optional runtime dependency with
`py -m pip install -r environment/requirements-ai.txt`. Run model integration
checks with `py -m pytest tests/unit/test_ai_model_integration.py -q`.

## Regenerating MATLAB exports

From the project root, run `matlab -batch "run('tools/export_matlab_ensembles.m')"`.
The exporter writes reference features and predictions with each JSON asset so
that Python/MATLAB numerical parity can be tested after re-exporting.

## LFP RPT models

`lfp_soh_ensemble.json` and `lfp_rul_ensemble.json` are portable randomized
regression forests trained by `tools/train_lfp_tree_models.py` from the UConn
64-cell LFP/graphite reference performance tests. Training uses an 80/20
whole-cell split with seed `20261110`; see
`results/metrics/lfp_ai_validation.json` for the held-out cells and metrics.
The current held-out SOH MAE is 2.66 percentage points (RMSE 3.34, R² 0.647).
For the selected three-feature RUL model, the development whole-cell holdout
reports 564-cycle MAE and 919-cycle RMSE. These holdout results were inspected
during feature development, so they are not final independent evidence. These initial results
are research evidence, particularly weak for precise RUL use, and do not make
the estimators suitable for safety decisions.

A stricter, separate evaluation holds out complete cycling protocol groups 7
and 9. It reports SOH MAE 2.50 percentage points (RMSE 3.09, R² 0.672) and
RUL MAE 543 cycles (RMSE 668); see
`results/metrics/lfp_ai_protocol_group_validation.json`. This shows RUL errors
remain substantial when testing on unseen aging conditions.

The selected RUL model was evaluated with leave-one-protocol-group-out cross-validation
across all 11 groups. The selected three-feature forest (cycles, SOH, and
past-only SOH fade rate) achieved 650-cycle MAE and 943-cycle RMSE; the former
five-feature model achieved 683-cycle MAE and 971-cycle RMSE. The four-RPT
linear slope baseline achieved 1,964-cycle MAE. The maximum forest error
remains about 4,608 cycles. This cross-validation comes from the same dataset
used to develop the model and is not external final-test evidence. The
and also favor the reduced features, but have been inspected during model
development. See `results/metrics/lfp_rul_group_cross_validation.json` and
`results/metrics/lfp_rul_baseline_comparison.json`.

A separate one-pack, 3,000-cycle external-source stress evaluation reports
546-cycle MAE, 658-cycle RMSE, and 1,946-cycle maximum error. Its labels are
defined by the dataset's final cycle, and one pack cannot establish pack-to-pack
generalization. It is distribution-shift evidence only, not an independent
end-of-life validation. See
`results/metrics/lfp_rul_external_pack_validation.json`.

The LFP SOH input contract is `cumulative_cycles`,
`pulse_resistance_ohm_mean`, and `pulse_soc_count`. The RUL contract adds
`soh_pct` and `soh_fade_pct_per_1000_cycles`, a trailing slope calculated from
current and earlier RPTs only. Pulse resistance is approximated from the first
pulse sample against its preceding sample; it is not separate `Re`/`Rct`
measurement. Both models emit research-only, warning-quality estimates.

The LFP SOC AI path remains disabled by ADR-004. Seville provides one cell only
and the UConn time series lacks temperature; the available data do not support
a cell-held-out validation of a temperature-aware SOC model. The supplied SOC
CNN-LSTM remains NMC-only. The documented LFP coulomb-counting/OCV-fusion
estimator remains the software SOC baseline until suitable independent LFP
reference data are available.

To reproduce preprocessing and training from the project root, run
`python tools/prepare_lfp_dataset.py --all` and then
`python tools/train_lfp_tree_models.py`. The preprocessing scan reads the
19 GiB UConn RPT portion and writes ignored derived tables under
`results/raw/lfp/`; original downloads stay local. The stricter group evaluation
uses `--split protocol-group` and writes its alternate models under
`results/raw/lfp/protocol_group_models/`.
