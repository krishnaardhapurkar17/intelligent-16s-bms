# Hardware Design Basis — 16S LFP BMS

Status: preliminary architecture, not fabrication release  
Current scope: software/design documentation, schematic review, BOM status,
non-simulation verification artifacts and portfolio evidence. PCB layout,
KiCad SPICE simulation, physical fabrication, battery connection, bench
testing and vehicle testing are excluded from this work revision. No
fabrication, electrical-safety or vehicle-qualification claim is made.

## Architecture decision

Use a battery-monitor/control PCB with an external pack power stage. The PCB
draft measures 16 cell groups, current through an externally rated Kelvin
shunt, and thermistors; supervises contactor sequencing; and provides an
isolated CAN interface. The active-balancing circuit remains a schematic
candidate but is deferred from the current build/procurement baseline because
its transformer is not approved for transportation use. Main
positive/negative contactors, precharge contactor and resistor, pack fuse,
current shunt and traction-current conductors remain external and unselected.
This keeps pack current out of the control PCB; it does not make the external
power stage safe or complete.

The contactor sequence is OFF -> PRECHARGE -> MAIN CONTACTORS -> RUN. A
hardware-inhibit input from the battery monitor must remove coil enable on a
configured protection alarm. Firmware may request contactors but may not
override the monitor fault inhibit. Loss of board power defaults every coil
output off. The load-side bus is monitored so software can check that
precharge reached its allowed differential before closing the main contactors.
Precharge timing and voltage thresholds remain unconfigured until load
capacitance, charger behavior and cell limits are established.

USB GND/shield shares pack-referenced BMS GND/VSS. Grounded USB service is
prohibited while the pack is connected; a live-pack isolated service interface
is deferred and not claimed in the current design.

## Candidate circuit partition

| Block | Preliminary selection | Boundary |
|---|---|---|
| 16-cell monitor/protector | TI BQ76952, configured for 16S LFP | Cell sense and protection configuration must follow the final cell datasheet and TI reference circuit. Its integrated passive balancing can remain available. |
| Low-level controller | ESP32-S3 module; separate from AI host | Runs the local state machine and contactor sequencing. AI/Linux remains advisory. |
| CAN | ESP32-S3 TWAI through reinforced TI ISO1042DWRQ1 | Classic CAN at 500 kbit/s is the draft protocol. Confirm the exact orderable variant, isolated supply budget, connector, termination and bus fault environment before release. |
| Pack switching | External positive/negative main contactors plus external precharge contactor and resistor | 12-V coil-control interface; TPS1H200A-Q1 protected switches are candidates if coil current is under 1.5 A steady. PCB outputs are control-only. |
| Current measurement | 100-µΩ external Kelvin shunt target to BQ76952 SRP/SRN filter | Use the TI-recommended 100-Ω/100-nF differential filter. Shunt package, thermal design, pulse rating and thresholds remain to be verified. No high-current copper is routed on this PCB. |
| Temperature | Three external 10-kΩ NTCs on BQ76952 TS1/TS2/TS3 plus board temperature | Confirm the NTC curve, placement, wiring and thresholds against the selected cell/module. |
| Active balancing | LTC3300-2-family circuit with 16 transformer channels is captured as a schematic study only | Deferred from the build/procurement baseline. Do not populate the Wurth 750312504 candidate without written approval for the intended use or replacement with a reviewed part. BQ76952 passive balancing is the only balancing capability retained in the current baseline; even that configuration requires cell-specific verification. |

## Selected cell basis and provisional operating envelope

- Project model data identifies EVE LF100LA Version A, 3.2 V / 100 Ah LFP.
  The project stores its rated data in
  `models/battery-parameters/eve_lf100la_vA.json`; that document cites a
  third-party-hosted copy of EVE's Version A specification, so the supplied
  cell lot's own controlled datasheet still needs to be checked before a
  production release.
- At 16S, nominal voltage is 51.2 V and the cell-spec endpoints imply 40.0 V
  (16 × 2.50 V) to 58.4 V (16 × 3.65 V). The BQ76952 16S example also uses a
  40-V minimum system voltage.
- Set an **engineering target** of 50 A continuous and 100 A for up to 30 s
  for the initial external BDU/shunt interface. This is a project-level
  derating choice informed by the 50-A software scenario and the cell's
  100-A continuous / 200-A, 30-s pulse maximums. It is not a validated vehicle
  load profile. Charge-current limit is independently set to 50 A pending
  charger and thermal review.
- Use 12-V auxiliary contactor coils as the initial interface assumption, with
  three control outputs and auxiliary contact feedback. This does not size the
  coils or approve a particular contactor. The selected parts must be rated
  for at least 60 V DC, the 50-A continuous / 100-A 30-s operating
  envelope, the actual pack fault current and the required DC interruption.
- The pack's prospective short-circuit current, external DC-link capacitance,
  operating temperature/thermal model and final coil loads remain unknown.
  Fuse interrupt rating, contactor breaking capacity, precharge resistor and
  shunt thermal selection must be based on those values before release.
- The project software's active-balancing model uses charge-only operation,
  requires a closed BDU, no protection fault, valid cell sensors, and cell
  temperatures below 45 C. Its provisional thresholds are 1% SOC spread to
  start, 0.5% to stop, and 1 A maximum transfer current. These are candidate
  system requirements, not validated cell limits or a hardware implementation.
- The supplied GMP pack sheet describes a separate 8S, 40-Ah product and its
  40-A/80-A BMS and 0.4-A active balance ratings are not transferred here.

## Design review gates

1. Verify the exact EVE LF100LA revision and cell lot, and confirm the
   provisional 50-A/100-A operating envelope against the vehicle/load profile
   before setting production protection thresholds.
2. Confirm the external main/precharge contactor coil ratings and load-side
   capacitance before selecting the driver, precharge resistor, timing and
   voltage-difference thresholds.
3. Select and calculate the external shunt, fuse, contactors, cable and
   connectors from continuous and fault currents.
4. Keep active balancing deferred. Only reconsider it after the transformer is
   approved for the intended use or replaced, and the complete 16S power stage,
   MOSFET/sense-resistor limits, harness protection, thermal behavior and
   fail-safe response receive an independent review. The 1-A transfer target
   remains provisional.
5. Review BQ76952 cell-tap order, input filtering, unused-pin treatment,
   supplies, thermistor circuits, alert polarity, autonomous protections and
   programmed settings against TI documentation.
6. PCB layout/DRC, independent hardware review, physical IMD/HVIL implementation,
   fabrication and physical validation are outside the current scope. A clean
   schematic ERC is not evidence of electrical safety, physical function,
   compliance or EV qualification. No board should be connected to a battery
   based on this unbuilt design.

## Primary references

- TI, [BQ76952 datasheet](https://www.ti.com/lit/ds/symlink/bq76952.pdf), Rev. B:
  3S–16S support, 16S example schematic, current-sense input filtering,
  thermistor behavior, autonomous protection, host interface and layout notes.
- TI, [TIDA-010208 reference design](https://www.ti.com/tool/TIDA-010208):
  10S–16S Li-ion/LFP monitoring, protection, current, temperature, high-side
  MOSFET control and reference schematics/BOM. Its FET power stage is not
  copied onto this external-contactor PCB.
- ADI, [LTC3300-2 product/datasheet](https://www.analog.com/en/products/ltc3300-2.html):
  basis for the on-board transformer-based active-balancing candidate; confirm
  the controlled datasheet, device qualification and exact 16S sub-stack
  implementation before use.
- Wurth, [750312504 transformer datasheet](https://www.we-online.com/components/products/datasheet/750312504.pdf):
  1:1, 3.46-µH nominal, 10.2-A typical saturation current and eight-terminal
  pin map. Its datasheet excludes transportation applications unless Wurth
  agrees; this is a schematic-development candidate only.
- Project source: `Intelligent_BMS_Word_Documents/02_System_Requirements_Specification.docx`,
  `03_System_Architecture_and_Design.docx`, and the supplied
  `GMP_Specs_LFP_25.6V_40AH.pdf`.
