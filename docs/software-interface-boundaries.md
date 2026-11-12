# Software interface and abstraction boundaries

These contracts support simulation and future integration design. They do not
claim a validated vehicle protocol, hardware protection, or production security.

## Message contract

`software/interfaces/message_schema.py` defines schema version 1.0. Messages
carry a type, Unix timestamp in seconds, quality state, value, engineering
unit, positive scale factor, and optional one-based cell index (1–16). Values
marked `INVALID` or `UNAVAILABLE`, and values classified `STALE`, must not be
used as current measurements. The freshness limit is supplied by the caller;
the helper does not synchronize clocks. This is transport independent and has
no CAN identifier, arbitration, serialization-width, or bus-timing allocation.

## Command authorization

`software/interfaces/command_authorization.py` models principal credentials,
roles, and command allow-lists to make allow/reject paths testable. The
credential is a plain simulation input; there is no hashing, key management,
replay protection, secure boot, cryptographic authentication, or cybersecurity
claim. It must not be used to authorize real equipment.

## Lifecycle records

`software/lifecycle/battery_passport.py` appends JSON Lines records containing
timestamp, event type, configuration, fault list, and degradation indicators.
SHA-256 hash chaining lets replay detect record edits and reordering. Without
an external hash anchor, it cannot detect whole-file replacement or tail
truncation. Durable storage, retention policy, external identity, and physical
battery passport compliance are not modeled.

## Related system boundaries

The PMU, IMU, TMU, SOP estimator, supervisory logic, and BDU remain simulation
abstractions. Their outputs depend on configured assumptions and input quality.
The BDU software model is the modeled protection authority; no hardware
independence, contactor dynamics, certification, or physical fault coverage is
demonstrated by these tests.

The PMU quality gate can identify missing, unavailable, saturated, out-of-range,
stale, or non-monotonic measurements. A plausible constant current bias cannot
be identified from one current channel alone; the PMU will use the measured
current for coulomb counting. The bias scenario demonstrates that propagation,
not bias diagnosis or redundant-sensor coverage.

The pack temperature diagnostic uses a provisional temperature coefficient to
vary cell resistance and applies static temperature scenarios. The coefficient
is not calibrated against the target cell, and the simulation does not model
heat generation, thermal mass, coolant flow, propagation, or thermal runaway.
Its temperature results are scenario behavior checks, not thermal validation.

## Battery state indicators

| Indicator | Meaning and units | Inputs and validity limits |
|---|---|---|
| SOC | State of charge, percent (0–100%). | Coulomb counting uses pack current in A, elapsed time in seconds, capacity in Ah, and an initial SOC. Fusion can also use cell voltage/OCV. A result is only meaningful while current and voltage measurements are valid and the capacity/initial state assumptions are appropriate. Coulomb-counting drift and LFP flat-region uncertainty remain. |
| SOH | Capacity health as percent of nominal Ah; resistance growth as percent over the reference resistance. | Capacity estimates assume a controlled 90% to 10% SOC discharge and known nominal capacity. The estimator uses 90% capacity SOH and 20% resistance growth as scenario flag thresholds and reports RMSE against simulated truth. Resistance growth uses a simulated current pulse and voltage response. These are separate indicators; they do not establish field aging or a universal end-of-life threshold. |
| SOP | Maximum charge/discharge current in A and power in W, plus limiting cell and validity status. | Requires 16-element arrays for voltage, resistance, capacity, SOC and temperature, valid PMU/TMU states, and finite pack current/voltage. It uses a first-order ohmic model without transient polarization. It is advisory and does not command protection. |
| SOS | State-of-safety summary: `NORMAL`, `WARNING`, `FAULT`, or `UNKNOWN`. | Summarizes BDU, PMU/sensor quality, thermal state, insulation state, and diagnostic category. Explicit modeled BDU/thermal/insulation faults take precedence; missing, invalid or unknown inputs yield `UNKNOWN`. The summary is advisory; the BDU remains the only modeled protection authority. |
| RUL | Remaining useful life in simulated equivalent cycles, reported for capacity and resistance degradation and as a limiting estimate. | Uses capacity SOH and resistance growth trajectories with synthetic accelerated degradation rates. End-of-life targets are 80% capacity SOH and 100% resistance growth. The output is a scenario estimate, not a field-life prediction or warranty. |

SOC, SOH, and SOP implementation details are in the SOC/SOH/RUL estimators
and `software/pmu/lfp_16s_state_of_power.py`. The SOS summary implementation is
`software/protection/lfp_16s_state_of_safety.py`. None of these indicators is a
certified safety, range, or power guarantee.

## Balancing models

The passive baseline models resistor bleed: current is `V/R`, power is `V*I`,
cumulative dissipated energy is the time integral of power in Wh, and removed
charge reduces that cell's SOC. A separate shared-capacitor-bank abstraction
transfers charge from the highest-SOC cell to the lowest-SOC cell, with
temperature, measurement-quality, charge-mode, protection-fault and BDU gates.
The comparison uses the same initial SOC vector and termination range. Both
models use an illustrative voltage-to-SOC curve. The active abstraction does
not simulate switching waveforms, capacitor ripple, parasitics, control
stability, a selected component, cell electrochemistry, or calibrated hardware
losses. The single-run time and energy comparison is behavioral evidence only.

## Diagnostic severity and evidence

The supervisory layer labels diagnostic severity as no threshold breach,
degradation indicated, or multiple indicators. Its evidence grade says whether
an estimator threshold was crossed. These are categorical descriptions of
simulated estimator outputs, not calibrated confidence probabilities and not
hardware protection commands. A threshold flag alone does not establish fault
cause or physical condition.

The supplied SOC CNN-LSTM is available through
`software/estimation/ai_battery_estimators.py`. It consumes a 30-sample, 10 Hz
window of voltage, current and temperature. On 21,013 held-out NMC069 windows
at 5°C, the integrated model reproduces 2.0014% SOC MAE (acceptance limit <3%)
and remains below 15% maximum absolute error. This is a combined cell/profile
and cold-temperature shift test on the supplied NMC dataset, not an LFP test.
The supplied SOH and RUL MATLAB ensembles are exported to Python tree assets and
match MATLAB predictions on 128 reference records per model within 1e-9.
Separate LFP SOH/RUL portable forests were trained from the UConn 64-cell RPT
data. Their whole-cell development holdout reports 2.66 SOH percentage-point
MAE and 564-cycle RUL MAE for the selected three-feature model. A separate
11-fold protocol-group evaluation reports 650-cycle RUL MAE; an external
single-pack dataset-boundary stress test reports 546-cycle MAE but does not
provide an independent end-of-life target. These results are research-only;
RUL uncertainty remains large. LFP
SOC AI stays disabled: Seville covers one cell and UConn has no temperature
channel. Feature contracts, label construction and scores are in
`models/ai/README.md`. All AI estimates serialize with warning quality and are
excluded from primary protection. The twofold noise check remains an additional
rule-based disturbance test, not AI evidence.

The mode-level BDU abstraction represents DRIVE, CHARGE, PARK, FAULT, and a
latched EMERGENCY_DISCONNECT state. It resolves operating-mode requests and
records the state; it does not command modeled contactors or replace the
existing protection BDU state machine. Emergency reset returns to PARK only
when the modeled protection fault is clear.

The BDU fault-injection scenario carries AI, communication, Linux, and
telemetry availability flags and confirms modeled overcurrent protection
still transitions to FAULT when all four are unavailable. The Linux and
telemetry flags model availability only; they do not simulate those services
or demonstrate physical hardware independence.
