# Requirements Traceability Matrix (RTM)

**Project:** Simulation-First 16S Intelligent Battery Management System

**Document ID:** GOV-003

**Revision:** 0.1

**Date:** 31 October 2026

**Status:** Working Draft

---

## 1. Purpose

This document establishes traceability between system requirements,
architectural design elements, software implementations, verification
procedures and supporting engineering evidence.

The matrix is maintained throughout project development to ensure
that every requirement has an identifiable implementation path
and a corresponding verification method.

## 2. Scope

This matrix covers:

- Functional requirements SYS-F-001 through SYS-F-025.
- Non-functional requirements SYS-NF-001 through SYS-NF-008.
- Verification scenarios SIM-001 through SIM-023.
- Supporting implementation and test evidence.
- Outstanding engineering actions.

## 3. Status Definitions

| Status | Meaning |
|---|---|
| Implemented | Implementation and supporting evidence exist. |
| Partially Implemented | Some required functionality exists, but the complete requirement is not satisfied. |
| Not Implemented | No qualifying implementation has been identified. |
| Not Verified | Implementation may exist, but sufficient verification evidence is unavailable. |

## 4. Functional Requirements Traceability

This section maps each functional requirement to its
implementation, verification method and evidence.
### 4.1 Battery Model and Diagnostic Requirements

| Requirement ID | Requirement | Design Element | Verification ID | Evidence Path | Status | Outstanding Action |
|---|---|---|---|---|---|---|
| SYS-F-001 | The model shall represent 16 series-connected cell instances. | Validated 16-cell pack configuration | SIM-001 | models/pack-model/cell_configuration.py; tests/unit/test_project_interfaces_and_lifecycle.py | Implemented | — |
| SYS-F-002 | Each cell shall support individually configurable initial SOC and at least one health-related parameter. | Independent per-cell SOC, capacity and resistance settings | SIM-002 / SIM-003 | models/pack-model/cell_configuration.py; tests/unit/test_project_interfaces_and_lifecycle.py | Implemented | — |
| SYS-F-003 | The pack model shall generate pack current and individual cell-voltage outputs for defined operating scenarios. | 16S discharge simulation and machine-readable cell outputs | SIM-001 | models/pack-model/lfp_16s_pack_simulation.py; results/metrics/lfp_16s_pack_baseline.csv | Implemented | — |
| SYS-F-004 | The system shall support controlled resistance-growth and capacity-reduction scenarios. | Per-cell health configuration and degradation experiments | SIM-002 / SIM-003 | models/pack-model/lfp_16s_weak_cell_test.py; models/pack-model/lf100la_capacity_fault.py; models/pack-model/lf100la_resistance_fault.py | Implemented | — |
| SYS-F-005 | The system shall support temperature variation or explicitly document the limitations of the selected model. | Temperature diagnostic and stated thermal-model limits | SIM-004 | models/pack-model/lfp_16s_temperature_diagnostic.py; docs/software-interface-boundaries.md | Implemented | — |
| SYS-F-006 | The system shall support sensor bias, noise and missing-measurement scenarios. | Measurement fault and sensor quality models | SIM-005 / SIM-006 / SIM-007 | models/pack-model/lfp_16s_sensor_bias_test.py; models/pack-model/lfp_16s_robustness_test.py; tests/unit/test_project_interfaces_and_lifecycle.py | Implemented | — |
| SYS-F-007 | A baseline threshold-based diagnostic shall be implemented before enhanced diagnostics. | Persistent cell-to-median voltage deviation baseline | SIM-001 | software/diagnostics/lfp_voltage_baseline.py; tests/unit/test_lfp_voltage_baseline.py; results/metrics/lfp_fault_baseline_comparison.json; results/metrics/lfp_fault_diagnostic_grid.json | Implemented | Thresholds remain provisional; broader grid is synthetic simulation evidence, not field validation. |
| SYS-F-008 | Enhanced diagnostics shall report a suspected cell or explicitly report no reliable localization. | Multi-signal diagnostic with explicit localization status | SIM-002 to SIM-008 | models/pack-model/lfp_16s_combined_fault_diagnostic.py; tests/unit/test_project_interfaces_and_lifecycle.py | Implemented | Root cause remains unconfirmed by simulation evidence. |
| SYS-F-009 | The system shall provide severity and confidence interpretation for diagnostic outputs. | Categorical severity and evidence-grade interpretation | SIM-008 | software/diagnostics/lfp_16s_supervisory_controller.py; tests/unit/test_lfp_16s_supervisory_fault_injection.py; docs/software-interface-boundaries.md | Implemented | Evidence grades are categorical, not calibrated probabilities. |
| SYS-F-010 | Balancing shall represent energy transfer or a documented equivalent. | Passive resistor-bleed model and separate generic shared-capacitor-bank transfer abstraction | SIM-009 | models/balancing/lfp_16s_passive_balancing.py; models/balancing/lfp_16s_switched_cap_active_balancing.py; models/balancing/run_active_passive_comparison.py; tests/unit/test_lfp_16s_switched_cap_balancing.py; results/metrics/lfp_16s_active_passive_balancing.json | Implemented | Active model is a software-level behavioral abstraction; it is not a component-level converter design. |
| SYS-F-011 | Balancing shall enforce eligibility checks and safety interlocks. | Passive and active controllers gate transfer on temperature, fault, sensor validity, charge mode and BDU state | SIM-010 | models/balancing/lfp_16s_switched_cap_active_balancing.py; tests/unit/test_lfp_16s_switched_cap_balancing.py; software/protection/lfp_16s_bdu_balancing_integration.py | Implemented | Active gating is verified in software tests only. |
| SYS-F-012 | The system shall evaluate SOC, SOH and RUL using documented features and targets. | LFP scenario estimators, chemistry-gated AI inference adapters, and LFP RPT forests for SOH/RUL | SIM-018 | models/pack-model/lfp_16s_soc_estimator.py; models/pack-model/lfp_16s_soh_estimator.py; models/pack-model/lfp_16s_rul_estimator.py; software/estimation/ai_battery_estimators.py; models/ai/lfp_soh_ensemble.json; models/ai/lfp_rul_ensemble.json; results/metrics/lfp_ai_validation.json; results/metrics/lfp_ai_protocol_group_validation.json; results/metrics/lfp_rul_group_cross_validation.json; results/metrics/lfp_rul_external_pack_validation.json; docs/decision-log.md | Partially Implemented | LFP SOC AI is explicitly unsupported by ADR-004. SOH/RUL estimates remain research-only; grouped RUL MAE is about 650 cycles with maximum error about 4,608 cycles. The separate one-pack test has dataset-boundary labels and does not establish end-of-life generalization. Acceptance criteria and more independent packs remain open. |
| SYS-F-013 | Each simulation shall log its scenario configuration, model version, random seed and metrics. | Per-stage execution manifests with literal and output-derived configuration snapshots, model hashes, generated artifact hashes, and seeded robustness repeatability | SIM-012 | tests/regression/run_regression.py; tests/regression/check_reproducibility.py; results/regression/regression_report.json; results/regression/reproducibility_report.json | Partially Implemented | Some simulations do not emit a complete machine-readable runtime configuration; externalize/version those inputs and register any untracked experiments. |
| SYS-F-014 | The system shall generate machine-readable outputs and plots. | Per-stage expected-artifact manifest and project-wide CSV/JSON/PNG integrity validator | SIM-001 | tests/regression/expected_artifacts.json; tests/regression/run_regression.py; tests/regression/validate_reports.py; docs/plot-review-record.md | Implemented | Re-run manifest and format checks after experiment output changes; review new plot families when added. |
| SYS-F-015 | The system shall define a transport-independent message schema suitable for future CAN integration. | Versioned BMS message contract | SIM-017 | software/interfaces/message_schema.py; docs/software-interface-boundaries.md | Implemented | CAN identifiers and bus timing remain future integration work. |
| SYS-F-016 | AI outputs shall not override modeled hardware protection decisions. | Supervisory controller and independent protection logic | SIM-017 | tests/unit/test_lfp_16s_bdu_independence.py; tests/unit/test_lfp_16s_supervisory_fault_injection.py | Implemented | Protection independence remains software-level evidence only. |
| SYS-F-017 | The system shall define SOC, SOH, SOP and SOS, including inputs, units and validity limits. | SOC/SOH/SOP estimators and advisory SOS summary | SIM-018 | docs/software-interface-boundaries.md; software/pmu/lfp_16s_state_of_power.py; software/protection/lfp_16s_state_of_safety.py | Implemented | — |
| SYS-F-018 | The PMU shall model current sensing, coulomb-counting input, overcurrent state and measurement quality. | PMU and current-sensing model | SIM-013 | software/pmu/lfp_16s_pmu.py; tests/unit/test_lfp_16s_pmu.py; tests/unit/test_lfp_16s_pmu_integration.py | Implemented | Hardware sensing and calibration remain outside simulation scope. |
| SYS-F-019 | The insulation monitor shall represent valid, warning, fault and unavailable states without claiming physical measurement. | Insulation monitoring abstraction | SIM-014 | software/diagnostics/lfp_16s_insulation_monitor.py; tests/unit/test_lfp_16s_insulation_monitor.py; docs/software-interface-boundaries.md | Implemented | Thresholds remain provisional simulation assumptions. |
| SYS-F-020 | The system shall represent thermal early-warning and thermal-runaway warning behavior as an abstraction. | Thermal monitoring and warning logic | SIM-015 | software/diagnostics/lfp_16s_thermal_management.py; tests/unit/test_lfp_16s_thermal_management.py; docs/software-interface-boundaries.md | Implemented | No physical thermal propagation or runaway model is claimed. |
| SYS-F-021 | The BDU shall represent drive, charge, park, fault and emergency-disconnect states. | BDU operating-mode state machine with emergency latch | SIM-016 | software/protection/lfp_16s_bdu_operating_mode.py; tests/unit/test_lfp_16s_bdu_operating_mode.py; docs/software-interface-boundaries.md | Implemented | Mode layer is an abstraction and does not command contactors. |
| SYS-F-022 | Primary protection shall operate independently of AI, Linux, communications and telemetry availability. | Independent simulated protection path with service-availability injection | SIM-017 | software/protection/lfp_16s_protection_bdu.py; tests/unit/test_lfp_16s_bdu_independence.py; tests/regression/validate_reports.py | Implemented | Evidence is limited to simulation logic; no hardware independence is demonstrated. |
| SYS-F-023 | Interface messages shall define cell index, units, scaling, timestamp, quality and stale-data behavior. | Versioned BMS message contract | SIM-017 | software/interfaces/message_schema.py; tests/unit/test_project_interfaces_and_lifecycle.py | Implemented | CAN serialization and clock synchronization remain unimplemented. |
| SYS-F-024 | The system shall simulate command authentication and update authorization without claiming production cybersecurity. | Simulation command authorization model | SIM-019 | software/interfaces/command_authorization.py; tests/unit/test_project_interfaces_and_lifecycle.py; docs/software-interface-boundaries.md | Implemented | Cryptographic authentication is explicitly outside scope. |
| SYS-F-025 | The system shall maintain a battery-passport-style simulation log of configuration, events, faults and degradation indicators. | Append-only JSON Lines records with SHA-256 hash-chain verification and deterministic replay | SIM-020 | software/lifecycle/battery_passport.py; tests/unit/test_project_interfaces_and_lifecycle.py | Implemented | Hash chaining detects record edits/reordering; external anchoring and durable storage are not modeled, so whole-file replacement or truncation cannot be ruled out. |

## 5. Non-Functional Requirements Traceability

| Requirement ID | Requirement | Design Element | Verification Method | Evidence Path | Status | Outstanding Action |
|---|---|---|---|---|---|---|
| SYS-NF-001 | A clean environment shall reproduce the core simulation. | Environment and dependency configuration | Fresh Python 3.13.7 virtual environment, full unit and regression suites | environment/requirements-core.txt; docs/clean-environment-verification.md; results/regression/regression_report.json | Implemented | Repeat after dependency or core simulation changes. |
| SYS-NF-002 | Configuration and simulation procedures shall be versioned and reproducible. | Per-stage source/configuration fingerprints and seeded robustness repeatability check | SIM-012 | tests/regression/run_regression.py; tests/regression/check_reproducibility.py; results/regression/ | Partially Implemented | Externalize/version configurations and repeat checks for unregistered simulations and environments. |
| SYS-NF-003 | Software shall use modular architecture and unit tests. | Modular software architecture, unit tests and measured branch coverage | 112 unit tests after the added assumption-model cases; full regression; coverage report | software/; tests/; results/regression/traceability_validation.json; results/metrics/unit_test_coverage.json | Partially Implemented | Aggregate line coverage is 79.91% (branch coverage 69.93%); protection BDU is 65.03%, thermal management 65%, supervisory controller 89.26%, passive balancing 96.59%, and AI adapter 81.35%. Coverage acceptance criteria have not been approved; rerun coverage after adding tests. |
| SYS-NF-004 | Reports shall state assumptions and limitations. | Assumptions and limitations in technical docs and every machine-readable metrics report | Automated report-content validation | docs/; results/metrics/; tests/regression/validate_reports.py | Implemented | Preserve report-content assertions as new outputs are added. |
| SYS-NF-005 | No physical validation or compliance claim shall be made without supporting evidence. | Verification governance | Documentation review | docs/ | Implemented | Maintain this restriction in all project reports and presentations. |
| SYS-NF-006 | Automotive feature abstractions shall have documented boundaries and source assumptions. | System architecture, interface boundaries and assumptions register | Design review | docs/assumptions-register.md; docs/software-interface-boundaries.md; docs/decision-log.md | Implemented | Revisit the register whenever model inputs, parameter sources or feature boundaries change. |
| SYS-NF-007 | The project shall not claim unmodeled sensor, physical or certification capabilities. | Model limitations and claims register | Documentation review | docs/ | Implemented | Preserve explicit limitations in project documentation. |
| SYS-NF-008 | Safety-related state transitions shall be deterministic and regression-tested. | BDU, supervisory and balancing state machines | Repeated identical BDU mode sequence plus fault/interlock transition tests | tests/unit/test_lfp_16s_bdu_operating_mode.py; tests/unit/test_lfp_16s_bdu_independence.py; tests/unit/test_lfp_16s_supervisory_fault_injection.py; tests/unit/test_lfp_16s_passive_balancing.py | Implemented | Re-run state-transition regression checks after changes to these state machines. |

## 6. Verification Scenario Traceability

| Verification ID | Scenario | Primary Requirement Coverage | Expected Evidence | Status |
|---|---|---|---|---|
| SIM-001 | Healthy matched pack | SYS-F-001, F-003, F-007, F-014 | 16-cell configuration, finite pack/cell CSV output, representative PNG/JSON artifact checks, and no-fault baseline diagnostic checks | Verified |
| SIM-002 | Increased cell resistance | SYS-F-002, F-004 | Configurable cell resistance and injected resistance-growth estimate checks | Verified |
| SIM-003 | Reduced cell capacity | SYS-F-002, F-004, F-012 | Weak-cell capacity injection and estimated capacity response checks | Verified |
| SIM-004 | Temperature variation | SYS-F-005, F-020 | Static temperature scenarios and diagnostic response checks; thermal-model limits documented | Verified |
| SIM-005 | Voltage sensor bias | SYS-F-006 | Cell 8 bias injection and localization; temperature bias scenarios also exercised | Verified |
| SIM-006 | Measurement noise | SYS-F-006 | Healthy-noise and excessive-noise scenarios with detection response | Verified |
| SIM-007 | Missing or stale measurements | SYS-F-006, F-023 | Missing/invalid-channel robustness and message freshness tests | Verified |
| SIM-008 | Simultaneous abnormalities | SYS-F-008, F-009 | Multiple-cell localization and severity checks; healthy/ambiguous results explicitly state no reliable localization | Verified |
| SIM-009 | Balancing SOC mismatch | SYS-F-010, F-011 | Lower-SOC cell exclusion and checked bleed current, power, SOC decrement and energy integration | Verified |
| SIM-010 | Balancing ineligible due to fault or temperature | SYS-F-011 | Fault, temperature, charge-mode and BDU interlock tests | Verified |
| SIM-011 | AI input distribution shift | SYS-F-012 | Supplied SOC CNN-LSTM evaluated on 21,013 held-out NMC069 windows at 5°C; acceptance MAE <3% and max absolute error <15%; Python parity tests also cover supplied SOH/RUL MATLAB exports | Verified |
| SIM-012 | Repeatability with identical configuration and seed | SYS-F-013, SYS-NF-002 | Two seeded robustness runs with matching CSV/JSON SHA-256 output hashes; environment and source version recorded | Verified |
| SIM-013 | PMU current-sensor bias, saturation or unavailability | SYS-F-018 | Biased current propagation into coulomb counting; saturation and unavailable-channel quality tests | Verified |
| SIM-014 | Insulation-status warning and fault | SYS-F-019 | Normal, warning, critical, unavailable, stale, and invalid measurement tests | Verified |
| SIM-015 | Thermal warning | SYS-F-020 | Warning/critical classification, spread, unavailable, and invalid-channel tests | Verified |
| SIM-016 | Expanded BDU states | SYS-F-021 | Drive/charge/park selection, protection-fault override, emergency latch and guarded reset tests | Verified |
| SIM-017 | AI, Linux or communications failure containment | SYS-F-015, F-016, F-022, F-023 | Modeled overcurrent trip with AI/Linux/communication/telemetry unavailable; schema freshness and quality tests | Verified |
| SIM-018 | SOC, SOH, SOP and SOS | SYS-F-012, F-017 | LFP SOC/SOH/RUL simulation scenarios; supplied AI inference and MATLAB parity tests; SOC held-out NMC test; SOP input/quality/derating tests; SOS normal/warning/fault/unknown tests; indicator inputs and limits documented | Verified |
| SIM-019 | Authentication and authorization | SYS-F-024 | Authorized, wrong-credential, wrong-role and unknown-command tests | Verified |
| SIM-020 | Lifecycle logging and replay | SYS-F-025 | Append/replay order and record validation tests | Verified |
| SIM-021 | External precharge R-C assumption model and blocked-path fault | SYS-F-021 | Ideal 58.4-V / 100-ohm / 2-mF model; reports threshold time, current, power and resistor energy; blocked path times out with main command off | Verified — analytical software model only; not KiCad SPICE or hardware evidence |
| SIM-022 | Dynamic-load SOC initialization error and rest OCV correction | SYS-F-012, SYS-F-017 | Synthetic pulse/regen profile with 15-percentage-point initial error; observable and flat-plateau OCV cases; metrics and plots | Verified — synthetic model only; not WLTP/UDDS or independent cell validation |
| SIM-023 | Software-level protection fault injection | SYS-F-016, SYS-F-021, SYS-F-022 | OV, UV, OT, overcurrent and invalid-measurement inputs produce FAULT and de-energized modeled outputs; 1-ms update interval | Verified — software logic only; no physical sensor, filter, driver, fuse, or contactor latency |

## 7. Traceability Maintenance Rules

1. Every requirement shall map to at least one design element and verification method.
2. An implementation shall not be marked Implemented solely because a related source file exists.
3. A requirement shall not be marked Verified until its acceptance criteria and test evidence have been reviewed.
4. Evidence paths shall identify actual repository files, not assumed directory locations.
5. Any requirement change shall be reflected in this matrix and the relevant governance documents.
6. Simulation evidence shall not be presented as physical hardware validation.
7. All outstanding actions shall remain open until supporting evidence is reviewed.
