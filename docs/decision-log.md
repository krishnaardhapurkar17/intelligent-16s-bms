
# Engineering Decision Log

## ADR-004: LFP SOC AI Scope

Status: Accepted for the current software release

Decision: Keep the supplied SOC CNN-LSTM restricted to its documented NMC
training domain. Do not enable it for LFP, and do not train or report an LFP SOC
AI model from the currently prepared datasets. Continue using the documented
LFP coulomb-counting/OCV-fusion software estimator as the LFP SOC baseline.

Rationale: The supplied SOC model was verified on held-out NMC069 sequences,
but that does not establish LFP performance. The available Seville records
represent one cell, and the UConn cycling dataset lacks cell temperature and
does not provide an independent cell-held-out SOC reference suitable for the
temperature-aware model. Protocol-derived coulomb-count labels alone would
not provide independent SOC ground truth.

Reopen when a multi-cell LFP dataset with voltage, current, temperature, and
independently checked SOC references is available. Require cell-held-out
validation and documented operating coverage before enabling the LFP AI path.

Evidence: `tests/unit/test_ai_model_integration.py`,
`models/ai/soc_evaluation_results.csv`, and
`models/ai/README.md`.

## ADR-005: LFP RUL Feature Reduction

Status: Accepted as a research-model update

Decision: Use cumulative cycles, current SOH, and past-only trailing SOH fade
rate for the LFP RUL forest. Remove pulse resistance and pulse SOC count from
the RUL feature vector; retain those signals in the SOH model.

Rationale: In 11-fold leave-one-protocol-group-out cross-validation, the
three-feature candidate reduced MAE from 683 to 650 cycles and RMSE from 971
to 943 cycles versus the five-feature model. Reused development holdouts also
favored the reduced feature vector. This is a modest improvement and does not
constitute external validation or establish production accuracy.

Evidence: `results/metrics/lfp_rul_group_cross_validation.json`,
`results/metrics/lfp_ai_validation.json`, and
`results/metrics/lfp_ai_protocol_group_validation.json`.

## ADR-006: External Contactor Pack Switching

Status: Accepted for the preliminary hardware architecture; current and voltage
targets are provisional and final ratings remain subject to review

Decision: Use the BMS PCB to monitor/control the pack and command external
positive and negative main contactors plus a separate precharge contactor and
resistor. Keep the main pack-current path, fuse, shunt and precharge resistor
off the controller PCB. Default coil outputs off. Require both a valid local
controller request and a battery-monitor hardware-inhibit path before
energizing contactors. The load-side bus voltage must be measured to supervise
precharge before closing the main contactors.

Rationale: The project cell model identifies EVE LF100LA Version A, and the
hardware draft sets a 50-A continuous / 100-A, 30-second target. External
contactors keep traction current off the controller PCB and leave fuse,
interruption, precharge and thermal coordination in a dedicated external BDU.
The existing BQ76952 is retained as the 16S cell-monitor/protector candidate;
the contactor design must use its documented alert/protection interface and
must not imply that its high-side FET pins directly drive contactor coils.

Evidence and open items: `hardware/design-basis.md` and
`hardware/circuit-definition.md`; TI's BQ76952 datasheet and TIDA-010208
reference design. Confirm the controlled LF100LA Version A cell data and load
profile; complete short-circuit coordination, contactor/precharge sizing,
external power-stage selection, and independent review before any hardware
release. A 16-channel LTC3300-2/Wurth active-balancer study is now captured in
the schematic, but is deferred from the build/procurement baseline. No
fabricated or physically validated design is claimed.

## ADR-007: USB Service Restriction

Status: Accepted for the current unbuilt design revision

Decision: Do not connect grounded USB service equipment while the battery pack
is connected to the BMS. Live-pack USB isolation redesign is deferred; the
schematic does not claim an isolated USB service interface.

Rationale: USB ground and shield share the pack-referenced BMS GND/VSS domain.
USB ESD protection is not galvanic isolation. A restrictive service boundary
is safer than assuming a grounded host can be connected to an energized pack.

Reopen if live-pack service is required. Add and independently review a
galvanically isolated interface before making that use case available.

Evidence: `hardware/kicad/controller_16s.kicad_sch`,
`hardware/requirements-status.md`, and `hardware/README.md`.

## ADR-008: Defer Active-Balancer Hardware

Status: Accepted for the current design/procurement baseline

Decision: Retain the LTC3300-2/Wurth 16-channel circuit as a schematic study
only. Do not procure or populate the Wurth 750312504 transformer candidate.
Active balancing is not part of the current build baseline.

Rationale: The transformer documentation excludes transportation applications
without manufacturer approval. The transformer, power stage, harness
protection, switching behavior and thermal limits have not been independently
qualified. The software active-balancing model remains behavioral and does not
validate this circuit.

Reopen only after written approval for the intended use or selection of a
reviewed replacement, followed by complete electrical, thermal, harness and
fail-safe review. BQ76952 passive balancing also remains subject to cell-specific
configuration review.

Evidence: `hardware/kicad/active_balancer_16s.kicad_sch`,
`hardware/design-basis.md`, and `hardware/requirements-status.md`.

## ADR-009: Bound Hardware Scope to Design Evidence

Status: Accepted for the current work revision

Decision: Keep the current deliverable to software/design documentation,
schematic review, BOM status and non-simulation verification artifacts. Do not
select external pack contactors, fuse, shunt or precharge parts without
controlled application data. Physical IMD/HVIL, PCB layout, KiCad SPICE
simulation, fabrication, battery hookup and physical validation are not part
of this revision.

Rationale: The actual cell lot, vehicle load profile, prospective fault current,
coil specifications, DC-link capacitance and thermal conditions are not
controlled inputs. Selecting safety-critical ratings without those inputs
would create unsupported design claims.

Reopen when the missing application requirements are available and a separate
hardware/PCB validation scope is authorized. This decision does not imply
electrical safety or hardware readiness.

Evidence: `hardware/requirements-status.md`,
`hardware/design-basis.md`, and `docs/requirements-traceability-matrix.md`.

## ADR-003: Active Balancing Software Abstraction

Status: Provisional simulation choice

Decision: Model a shared switched-capacitor bank that selects the highest-SOC
and lowest-SOC cells for a charge-transfer cycle. Keep resistor bleed as the
passive reference. Use the same initial SOC vector and 0.5 percentage-point
termination range for the comparison.

Evidence: `results/metrics/lfp_16s_active_passive_balancing.json` and its CSV
and figure. The current illustrative run reaches the termination range in
424.25 simulated hours versus 675.10 hours for resistor bleed. Modeled losses
are 1.76 Wh and 429.33 Wh, respectively.

Limitations: The SOC-voltage mapping, transfer current, equivalent resistance,
thermal constants and capacity are assumptions. The model does not represent
switching waveforms, capacitor ripple, parasitics, control stability, EMI,
component ratings, or a selected product topology. These results support only
software-level comparison under one scenario; they are not hardware claims.

## ADR-001: LFP Cell Chemistry and Electrochemical Model

Status: Provisional
Decision: LFP chemistry
Reference parameter set: PyBaMM Prada2013
Primary model: SPMe

### Parameter provenance
- LFP positive electrode: Prada et al. (2013)
- Graphite negative electrode: Chen et al. (2020)
- LFP OCP: Afshar et al. (2017)
- Exchange current density: Kashkooli et al. (2017)

### Rationale
Prada2013 provides a documented LFP
electrochemical parameterization in PyBaMM.

SPMe is selected as the initial electrochemical
model because it includes electrolyte dynamics.

### Limitations
The parameter set represents a reference cell,
not necessarily the target commercial cell.

The model requires further validation against
appropriate experimental data.

### Future work
- Confirm target cell manufacturer and model.
- Verify parameter applicability.
- Evaluate temperature dependence.
- Evaluate degradation parameterization.
- Construct the 16S pack model.
