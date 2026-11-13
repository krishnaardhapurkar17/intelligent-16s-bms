# Portfolio evidence register

This register maps the project to the engineering-audit checklist. It
distinguishes captured design, software-model evidence, bounded scope decisions
and work that remains unverified. The project is simulation-first with a draft
control-board schematic; it is not a fabricated, safety-certified, or
vehicle-qualified BMS.

## 1. System architecture and schematic

| Checklist item | Current evidence | Status / boundary |
|---|---|---|
| System block diagram | `hardware/architecture.svg` | Shows the cell stack, BQ76952, ESP32-S3, I2C/ALERT, isolated CAN, host, inhibit logic, and external power stage. The CAN and low-voltage domains are architectural, not validated isolation/layout evidence. |
| Cell-sensing inputs and filters | `hardware/kicad/afe_16s.kicad_sch`; `hardware/requirements-status.md` | Filter network is captured from the design basis. Harness protection, open-wire detection, NTC curve, and input fault behavior are not verified. |
| Service/isolation boundary | `hardware/kicad/controller_16s.kicad_sch`; `hardware/requirements-status.md` | Grounded USB service is prohibited while the pack is connected. Live-pack USB isolation redesign is deferred; USB protection is not galvanic isolation. |
| Passive and active balancing | KiCad schematic; `models/balancing/` | Passive balancing remains in the schematic baseline subject to cell-specific verification. The active-balancer is a schematic/software study, deferred from build and procurement; its transformer must not be populated without approval or replacement and independent review. |
| BDU, contactors, and precharge | `hardware/circuit-definition.md`; `software/protection/lfp_16s_protection_bdu.py` | Control logic and software sequencing exist. External power-stage parts are unselected; coil/contact ratings, fuse coordination, DC-link load, and precharge values are examples or provisional assumptions only. |
| IMD and HVIL | `software/diagnostics/lfp_16s_insulation_monitor.py`; RTM SYS-F-019 | The insulation-monitor feature is a software abstraction only. Physical IMD/HVIL and vehicle integration are outside this revision; no physical protection capability is claimed. |

## 2. PCB and physical design

| Checklist item | Current evidence | Status / boundary |
|---|---|---|
| KiCad schematic ERC | `hardware/kicad/integrated_erc.txt` | Current `--severity-all` report has 0 errors and warnings. The project still excludes single-use global labels, four-point joins, footprint filters, and SPICE-model issues. ERC is not DRC, simulation, or electrical approval. |
| PCB source | `hardware/kicad/intelligent_16s_bms.kicad_pcb` | Footprints are present; routing, vias, zones, and DRC evidence are absent. PCB work is outside this revision's scope. |
| Creepage, clearance, impedance, thermal layout | `hardware/requirements-status.md` | Not proven; no routed layout or independently reviewed stackup/constraints are available. |
| BOM and qualification | `hardware/bom/intelligent_16s_bms_draft.csv`; `hardware/bom/README.md` | Integrated BOM is a non-procurement draft. Legacy page BOMs do not match the integrated design. Exact orderable variants, ratings, sourcing and qualification are not approved; active balancing is deferred from the build baseline. |

## 3. Algorithmic and control models

| Checklist item | Current evidence | Status / boundary |
|---|---|---|
| Cell ECM | `models/pack-model/lf100la_ecm_simulation.py`; `models/battery-parameters/lf100la_ecm_assumptions.json` | First-order Thevenin model with an OCV table and one RC branch. Parameters are explicitly synthetic and not manufacturer-validated; temperature dependence is not implemented. |
| SOC under a dynamic load and wrong initial SOC | `software/estimation/soc_drive_cycle.py`; `tools/run_soc_drive_cycle_experiment.py` | New deterministic synthetic pulse/regen profile compares coulomb counting and one rest-time OCV correction with a 15-percentage-point initial error. It is not WLTP/UDDS and has ideal sensing. The results show correction can reduce error in an observable OCV region, while the flat mid-SOC plateau rejects it. |
| State machines | `docs/bdu-state-machine.md`; associated unit tests | Protection-BDU and operating-mode machines are documented separately, matching the code. They do not model physical coil/contactor dynamics; balancing remains a separate supervisor. |

## 4. Verification, fault injection, and reproducibility

| Checklist item | Current evidence | Status / boundary |
|---|---|---|
| Software protection fault injection | `tests/unit/test_lfp_16s_protection_bdu_unit.py`; full unit suite | Software tests cover voltage, temperature, overcurrent, invalid inputs, precharge transition, timeout, and fail-open outputs. An input already crossing a configured threshold is not a sensor-to-contactor hardware response-time measurement. |
| Analytical precharge waveform | `tools/run_precharge_assumption_sim.py`; `results/metrics/precharge_assumption_simulation.json`; `docs/figures/precharge_assumption_waveforms.png` | Ideal source + R + C model using the documented 58.4 V / 100 ohm / 2 mF / 3 V / 1 s example. It reaches the delta threshold at about 0.594 s; a blocked path times out with the main-contactor command off. This is not KiCad SPICE or a component model. |
| SOC initialization experiment | `results/metrics/soc_drive_cycle_initialization.json`; `docs/figures/soc_drive_cycle_initialization.png` | Reproducible software-model result. The synthetic profile, ideal sensing, and limitations are stated in the report. It is not a standardized drive-cycle or independent cell-validation result. |
| NTC-curve simulation, AFE open-wire behavior, fuse/contactor trip curves, short-circuit waveform, hardware timing | None | Not implemented or verified. A selected sensor, AFE model, fuse, contactors, load, and validated acceptance criteria are prerequisites. |
| KiCad SPICE simulation | None | KiCad is installed, but no schematic simulation has been run. This work revision intentionally leaves simulation untouched; ERC's ignored SPICE-model check is not a simulation result. Do not present the analytical Python precharge model as a KiCad run. |
| Requirements traceability | `docs/requirements-traceability-matrix.md` | Existing requirements and software scenarios are mapped. New software-model experiments are recorded there; physical evidence remains explicitly open. |

## Reproduction commands

From the project root, run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe tools\run_precharge_assumption_sim.py
.\.venv\Scripts\python.exe tools\run_soc_drive_cycle_experiment.py
.\.venv\Scripts\python.exe tools\run_software_fault_injection_report.py
```

Every reported result must retain its model boundary. Simulation evidence is
not a substitute for calibrated cell data, independent electrical review, or
physical validation.
