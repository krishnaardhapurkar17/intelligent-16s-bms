# Hardware Circuit Definition — Draft for KiCad Capture

Revision 0.2 — assumption-based engineering draft, not a fabrication release

This file turns the project's selected 16S EVE LF100LA cell model and software
BDU sequence into an electrical design basis. The integrated KiCad schematic
captures the AFE, protected input, dual low-voltage rails, reinforced isolated
CAN, USB and ADC protection, BDU permit/coil drivers, watchdog fault latch and
a 16-channel active-balancing candidate. Ratings and release gates below still
require validation.

## Pack and operating targets

| Item | Draft value | Basis |
|---|---:|---|
| Cell arrangement | 16S1P LFP | Project cell model |
| Cell | EVE LF100LA Version A, 100 Ah, 3.2 V nominal | `models/battery-parameters/eve_lf100la_vA.json` |
| Pack nominal voltage | 51.2 V | 16 × 3.2 V |
| Cell-spec endpoints | 40.0–58.4 V | 16 × 2.50–3.65 V; absolute operating boundaries, not normal trip settings |
| BMS operating target | 50 A continuous, 100 A up to 30 s | Initial project envelope; lower than cell max and aligned with software scenario |
| Charge operating target | 50 A continuous | Initial limit; confirm against charger and thermal design |
| Auxiliary supply | 12 V nominal | Fused, TVS-clamped and reverse-polarity-protected input is captured; validate against the actual vehicle transient/load profile |
| Cell monitor | TI BQ76952 | Supports 3S–16S, autonomous monitor/protection and passive balance |
| Local controller | ESP32-S3-WROOM-1 | Local state machine; AI host and Linux are supervisory only |
| CAN | 500 kbit/s classic CAN, isolated | One physical-layer port; CAN-FD not required by current interface |

### Provisional external power-stage examples

These are calculation examples to complete the draft, not selected parts or
validated limits:

- **Precharge:** assume a 58.4-V maximum pack and 2.0-mF DC link. A 100-Ω
  resistor gives 0.584 A initial current and a 0.20-s time constant. Ideal
  95% charge takes about 0.60 s; energy per charge is
  `0.5 × C × V² = 3.41 J`, with 34.1 W initial resistor power. A resistor
  pulse-energy rating of at least 7 J is a provisional 2× margin target. Use a
  3-V bus-delta close threshold and 1-s timeout only as firmware starting
  values. Recalculate from the actual capacitance, leakage, wiring, repeated
  cycling, resistor derating and contactor timing.
- **Pack fuse:** a 100-A, ≥100-VDC fuse is a placeholder for the 50-A
  continuous / 100-A 30-s envelope only. Its DC interrupt rating must exceed
  measured prospective pack fault current at maximum voltage, and its time
  curve must coordinate with the selected contactors and wiring.
- **Main shunt:** at 100 µΩ, `I²R` is 0.25 W at 50 A and 1 W at 100 A. These
  numbers do not include ambient, mounting, pulse repetition, tolerance or
  fault current.

The idealized software-level precharge calculation is reproducible with
`tools/run_precharge_assumption_sim.py`; its CSV, JSON metrics and waveform are
stored under `results/metrics/` and `docs/figures/`. It does not simulate the
KiCad schematic, a vendor component model, a loaded DC link, contactor motion,
or physical behavior.

The LF100LA Version A data currently cited by the repository is a third-party
hosted copy of an EVE specification. Obtain and archive the controlled cell
revision used for any production release. A current EVE product page reports a
different 102-Ah LF100LA variant; do not silently mix that variant's values
with the project's 100-Ah Version A model.

## Functional circuit blocks

### Cell monitoring

- Bring out VC0 through VC16 in sequence from pack negative to pack positive.
- Use the captured keyed, locking 18-circuit Micro-Fit 3.0 connector for
  VC0–VC16 (pin 18 reserved). Confirm the mating harness, pin order, wire gauge,
  tap fusing, insulation and insertion sequence against the selected pack.
- Implement the BQ76952 16S input network from TI's Figure 16-2, including the
  prescribed input resistors/capacitors, BAT supply path, REG decoupling,
  wake/ship controls and unused-pin treatment. Do not invent a shortened
  repeated filter without checking the reference design and pin limits.
- For the external-contactor architecture without BQ high-side protection
  FETs, connect PACK to stack positive through 10 kΩ and LD to VSS, as TI
  recommends. Add the recommended 10-MΩ BREG-to-VSS leakage path. REGIN is
  intentionally left NC only while REG0/REG1/REG2 remain disabled and the MCU
  is powered from the separate auxiliary converters; confirm this choice
  against the final BQ configuration and controlled reference design.
- Route each tap as a quiet sense path; keep balance-current loops out of the
  sense path. Provide test points for all 17 tap nets and cell-monitor rails.
- Program protection thresholds from cell limits with measurement error,
  temperature and delay margins; 2.50/3.65 V are datasheet endpoints and are
  not approved software trip values.

### Current and temperature

- Use an external four-terminal 100 µΩ shunt, nominal 5 W or higher, in the
  pack-negative path. At the draft envelope it produces 5 mV/0.25 W at 50 A
  and 10 mV/1 W at 100 A; verify continuous thermal conditions, overload
  pulse, tolerance and temperature coefficient when selecting the part.
- Connect only the shunt Kelvin pair to the PCB. Use the TI-recommended
  symmetric 100 Ω series resistors and 100 nF differential capacitor at
  SRP/SRN, with short matched routing on the same side of the BQ76952.
- Provide three 10-kΩ cell-stack NTC inputs on BQ76952 TS1/TS2/TS3 (matching
  TI's 16S example) and one separate board-temperature input to the MCU. Freeze
  the NTC beta/R-T curve, sensor attachment method, open/short diagnostics and
  placement before thresholds are configured.

### Active balancing

- Active balancing is required and is targeted for integration on this PCB.
  The draft sheet now captures three LTC3300-2-family controllers: U30 covers
  cells 1–6, U31 cells 7–12 and U32 cells 13–16. Sixteen transformer channels
  transfer energy from a selected cell to its local sub-stack; BQ76952 passive
  bleed remains a separate supplementary function. Each channel uses a
  provisional 25-mΩ current-sense resistor and two 100-V MOSFET candidates.
- A provisional 1:1 Wurth 750312504 is shown per channel. Its 3.46-µH nominal
  inductance and 10.2-A typical saturation current are candidate data only.
  Its datasheet says it is not intended for transportation applications absent
  Wurth agreement, provides only a 500-VDC insulation test, and requires pad
  pairs 1+2, 4+5, 6+7 and 9+10 to be commoned. The schematic now maps those
  actual pad numbers; the PCB footprint remains unassigned. Replace or obtain
  written manufacturer approval and independently review its insulation and
  thermal suitability before release.
- The schematic uses 47-µF nominal cell bypass capacitors, with at least
  12-µF effective capacitance at bias/temperature as a provisional design
  target. U30/U31 use the next-higher cell boost rail; U32 uses the
  datasheet-based boost diode/resistor/flying-capacitor circuit. Transformer
  snubbers are unpopulated; 330 Ω + 100 pF is only a starting point for
  ringing/thermal characterization.
- Each LTC device has a TI ISO7762F-Q1 isolated SPI/permit interface referenced
  to its local V−. A local transistor can force its LTC watchdog input high to
  pause balancing when permit is removed. The LTC serial watchdog is a
  second, independent balancing timeout (0.75–2.25 s specified, 1.5 s
  typical). Verify exact orderable variants, isolated-domain supplies, SPI
  timing, address map, watchdog refresh and startup/fault states.
- J30 is intentionally a separate high-current balance-tap harness; its
  `BAL_TAP0..16` nets are not joined to the AFE `TAP_1..16`/`VC0..16` PCB nets.
  At system level, connect both harnesses to the same cell-stack nodes, with
  balancing current carried by J30 and only sense current on the AFE harness.
  Define the pack-side branch point, wire gauge, tap protection and connector
  derating before release.
- The current-sense relationship predicts under 1 A average transfer for
  1:1 turns and S=4–12 with the 25-mΩ provisional setting; this is not a
  measured or guaranteed 1-A rating. Verify switching waveforms, saturation,
  MOSFET gate drive/RDS(on), resistor pulse rating, cell bypass current,
  transformer temperature and harness ampacity. One channel maximum at a time
  is a firmware policy, not hardware arbitration.
- The software model's provisional policy is charge-only, closed BDU, no
  protection fault, valid cell sensors, cell temperatures below 45 C, start at
  1% SOC spread, stop at 0.5% SOC spread, and a 1-A maximum transfer current.
  These model settings are candidate system requirements, not validated cell
  limits or a guaranteed hardware rating. The transformer candidate is not
  automotive-approved. No PCB or physical validation has been performed.

### Contactor and precharge control

- Keep the main positive/negative contactors, precharge contactor, precharge
  resistor, pack fuse, shunt and all traction current off this PCB.
- Expose three 12-V-coil control outputs (MAIN+, MAIN−, PRECHARGE), three
  auxiliary-contact feedback inputs and the load-side DC-link measurement.
- Coil outputs default off by hardware pull-down and require both a valid local
  controller command and an independent BQ76952 protection-permit path.
  A protection alert or loss of board power must de-energize outputs. No
  software override may defeat the hardwired fault inhibit.
- Use three protected automotive high-side drivers on the 12-V coil supply,
  initially targeting coils below 1.5 A steady-state. A TI TPS1H200A-Q1 per
  output is the candidate; verify coil inrush/hold current, thermal dissipation,
  inductive clamp behavior and supply transients against the chosen contactors.
  Provide separate output pins, test points and driver fault feedback.
- Gate each MCU output through an external hardware AND function with a
  BQ76952-derived `BMS_PERMIT` (permit asserted only while monitor power is
  valid and no configured protection fault is active). Pull all enables low;
  add a hardware watchdog that removes the shared permit on missing heartbeat.
- The software-defined order remains OFF → PRECHARGE → MAIN CONTACTORS → RUN.
  The three outputs are mutually exclusive where required; main closure is
  permitted only after measured bus delta is below its configured threshold.
- The external contactors must be rated for at least 60 V DC and the draft
  operating current, with DC breaking capability based on pack prospective
  fault current. Fuse interrupt rating and contactor coordination remain an
  explicit release gate.
- As a schematic-level precharge example, assume 2.0 mF DC link at 58.4 V:
  use 100 Ω for 0.584 A initial current, 0.20 s time constant and 3.41 J
  charge energy. Ideal 95% charge is about 0.60 s. A 3-V delta threshold and
  1-s timeout are initial software targets only; calculate the actual resistor
  pulse rating and timing from the vehicle bus capacitance and fault case.

### Power, controller and communications

- Treat the auxiliary input as a provisional 9–16-V steady profile around
  12 V nominal. Bring it in through the captured 10-A fuse, SM8S33A
  TVS, LM74700-Q1 ideal-diode controller and BUK9Y22-100E N-channel pass FET.
  Separate LM5164-Q1 channels generate the 3.3-V controller and 5-V CAN-isolator
  rails. Check fuse coordination, TVS clamp/energy, inrush and FET/buck thermal
  performance against the actual vehicle environment; no load-dump or surge
  validation is claimed. Compare the BQ76952 stack supply pin-by-pin with TI's
  16S monitor reference before release.
- BQ76952 and MCU share pack-negative logic ground. ISO1042-Q1 and UCC33421-Q1
  provide the reinforced isolated CAN interface and isolated bias supply;
  ESD2CAN24-Q1 protects CANH/CANL. UCC33421-Q1 is rated for 5 V at 300 mA
  (1.5 W); reserve no more than 100 mA (0.5 W) for the isolated load until
  worst-case ISO1042-Q1, termination and auxiliary loads are calculated. The
  ISO1042-Q1 datasheet gives 360 mW maximum side-2 power dissipation under its
  specified 50-Ω repetitive test at 5.5 V; the 0.5-W budget is a conservative
  first-order allowance, not a substitute for application load calculation.
  The ISO1042DWRQ1 is the reinforced-isolation variant; do not substitute the
  ISO1042BDWRQ1 basic-isolation variant. Preserve the isolation barrier and
  required creepage/clearance in PCB layout.
- ESP32-S3 native TWAI connects to ISO1042-Q1. CANH/CANL, CAN reference, a
  shield pin with 1-MΩ/1-nF HF bond, and removable 120-Ω termination are
  captured. Fit termination only at a physical bus endpoint.
- Provide a service/programming connector and a safe service mode that cannot
  energize contactors by itself.

### Provisional ESP32-S3 signal allocation

| ESP32-S3 GPIO | Draft signal | Direction | Notes |
|---:|---|---|---|
| 8 / 9 | BQ76952 SDA / SCL | Bidirectional / output | Pack-negative referenced I²C; verify pull-ups and voltage levels against the BQ76952 interface circuit. |
| 17 / 18 | CAN_TX / CAN_RX | Output / input | Native TWAI to ISO1042-Q1. |
| 4 / 5 / 6 | MAIN_POS_REQ / MAIN_NEG_REQ / PRECHARGE_REQ | Output | Pulldowns; each must be gated by hardware `BMS_PERMIT`. |
| 7 / 10 / 11 | MAIN_POS_FB / MAIN_NEG_FB / PRECHARGE_FB | Input | Auxiliary-contact feedback; add input protection/filtering and define active levels. |
| 12 | AFE_ALERT | Input | Fault interrupt plus independent hardware permit path; configure BQ ALERT active-low and verify the startup state. |
| 13 | WD_HEARTBEAT | Output | 20-Hz candidate target for TPS3430-Q1. Its WDO is a timed pulse captured by the cross-coupled NAND fault latch. GPIO42 `WD_REARM_N` must pulse low only after firmware confirms healthy heartbeat; startup defaults to inhibit. |
| 1 | DC_LINK_SENSE | ADC input | Divider/protection from load-side bus; values based on 58.4-V max plus transients and ADC range. |
| 2 | PCB_TEMP | ADC input | Board NTC divider; keep distinct from BQ cell thermistors. |
| 19 / 20 | USB D− / D+ | USB interface | Service programming/debug only; must not enable coils during reset/service. |

Avoid using ESP32-S3 strapping pins for safety-critical output control. Final
pin allocation must be cross-checked against the exact module revision,
boot behavior and firmware before schematic freeze.

## Captured component schedule (verify orderable suffixes and packages)

| Ref | Candidate | Use | Selection caveat |
|---|---|---|---|
| U1 | TI BQ76952PFB | 16S monitor/protector | Captured; verify against TI Figure 16-2/16-3 and set LFP thresholds after cell review |
| U2 | ESP32-S3-WROOM-1-N16R8 | Local MCU | Captured; confirm module variant, supply, RF keepout, lifecycle and firmware pin map |
| U3 | TI ISO1042DWRQ1 | Reinforced automotive isolated CAN physical layer | Captured; verify exact variant, bus topology, isolation and PCB barrier/layout |
| U4–U6 | PC817 feedback optocouplers | External contactor auxiliary-contact feedback | Captured; verify CTR, isolation rating, input resistor, contact polarity and temperature |
| U7–U9 | TI TPS1H200A-Q1 | Protected automotive coil switches | 4–40 V supply range; each is a 2-A-class device; verify real coil inrush/hold current and heat |
| U12–U14 | TI SN74LVC1G08-Q1 | Per-coil MCU request AND BMS permit gates | Confirm input thresholds and fault-default levels for `BMS_PERMIT` and MCU requests |
| U20/U21 | TI LM5164-Q1 | 12-V to 3.3-V and 5-V regulators | Captured; verify inductor, control values, transient input and load/thermal margins |
| U22/Q1/F1/D2 | TI LM74700-Q1, Nexperia BUK9Y22-100E, input fuse, Littelfuse SM8S33A | Auxiliary reverse polarity and transient protection | Captured candidate values; verify surge, pulse and thermal ratings |
| U17 | TI UCC33421-Q1 | Reinforced isolated 5-V CAN bias converter | 300-mA / 1.5-W datasheet output capability; 100-mA / 0.5-W provisional isolated-load budget; verify actual load and derating |
| D4 | TI ESD2CAN24DCKRQ1 | CANH/CANL transient protection | Captured; place by CAN connector and verify ground/shield return layout |
| U18/D5 | TI TPD4E02B04Q1 / TPD1E10B06DYARQ1 | USB D+/D− and VBUS ESD protection | Captured; verify pinout and place by service connector |
| D6/D7 | Nexperia BAT54H-Q | Load-voltage ADC rail clamps | Captured; verify leakage, transient current and MCU ADC absolute maximum |
| R22/R26 | 10 kΩ / 10 MΩ | BQ76952 PACK input / BREG leakage path | Captured per TI application guidance; verify REGIN/REG0 configuration and final BQ reference design |
| J1/J2 | Molex Micro-Fit 3.0, 18-circuit / 4-circuit | Cell taps and shunt Kelvin harnesses | Captured footprints; verify matching harness contacts, wire and insertion sequence |
| U30–U32 | LTC3300ILXE-2#WPBF candidate | 16S active-balancer controllers | 6/6/4-cell groups; verify qualification, exact 16S reference design and fault response |
| U33–U35 | TI ISO7762F-Q1 candidates | Isolated SPI/permit interfaces for balancers | Verify exact orderable/package and isolation-domain layout |
| T30–T45 | Wurth 750312504 candidate | 1:1 cell-to-stack transformer channels | Correct pad numbers captured; no footprint assigned; datasheet excludes transportation use absent approval |
| Q30–Q61 / R301–R332 | BUK9Y22-100E / 25-mΩ candidates | Active-balancer switching and peak-current sensing | Verify gate-drive RDS(on), SOA, package pin map, pulse/thermal rating and actual part qualification |
| J30 | Molex Mini-Fit Jr 20-position candidate | Separate active-balance tap harness | Verify mating parts, tap wire ampacity/fusing and connector thermal derating |
| RSH1 | 100 µΩ, four-terminal, ≥5 W shunt | Current measurement, external | Confirm pulse/thermal derating and calibration plan |
| TH1–TH3 | 10-kΩ NTC, candidate Semitec 103-AT | Cell-stack temperature | Confirm actual curve and attachment/insulation method |
| TH4 | 10-kΩ NTC or board sensor | PCB temperature | Select part and place away from local heat sources |
| QD1–QD3 | Protected low-side drivers or rated MOSFET stages | External 12-V coil control | Pick only after coil current/inrush and suppression data are known |
| K1–K3 | External 12-V DC contactors | Main positive, main negative, precharge | Select exact DC load-break/fault ratings from application and fault study |
| F1 | External pack fuse | Short-circuit protection | Must interrupt prospective fault current at pack maximum voltage |
| RPRE | External precharge resistor | DC-link charging | Calculate from DC-link capacitance, initial delta, permitted time and pulse energy |

## KiCad implementation and release checks

1. Verify the captured BQ76952 cell-monitor circuit against TI's controlled 16S
   reference schematic and final OTP configuration, especially REGIN/REG0,
   PACK/LD, BREG, RST_SHUT, the cell-input filter, and unused-pin treatment.
2. Review the captured automotive input protection, isolated CAN supply/ESD,
   USB/VBUS and ADC clamps, MCU, NTCs, shunt filter, BDU gates, watchdog, smart
   coil switches, feedback and load-side measurement against datasheets.
3. Finalize project symbols/footprints and assign exact orderable parts.
4. Place and route a control PCB with cell-input connector separation, analog
   quiet zone, isolated CAN barrier, RF keepout, connector strain relief and
   clearly marked high-voltage sense boundaries. High-current path is excluded.
5. Run KiCad ERC and DRC, resolve all actionable errors, export BOM, schematic
   PDF, fabrication plots and assembly drawings, then get an independent
   electrical design review.
6. Stop at the unbuilt design package per the owner's budget. No physical
   battery hookup, fabricated-board validation or EV qualification is claimed.

## Design release gates still required

- Controlled LF100LA cell datasheet/lot confirmation.
- Cell-specific charge/discharge limits, temperature limits, and protection
  margins; pack charger/load profile and target vehicle requirements.
- Prospective short-circuit current, fuse and contactor coordination.
- Actual auxiliary and contactor coil specifications.
- DC-link capacitance and precharge resistor/timing calculation.
- Shunt part/thermal analysis and current calibration plan.
- NTC curve, number/locations, isolation attachment details.
- Active balancing: a 16-channel LTC3300-2-family candidate is captured, but
  the controller/transformer qualification, transformer transportation-use
  approval, footprint, switching/pulse/thermal limits, harness fusing and
  independent electrical review remain open.
- PCB manufacturability and safety review; physical validation is excluded by
  the owner's scope, so the design must remain labeled unvalidated.

## Design references

- TI BQ76952 datasheet, especially 16S monitor examples in Figures 16-1 to
  16-3 and current-sense/layout guidance: <https://www.ti.com/lit/ds/symlink/bq76952.pdf>
- TI TIDA-010208 10S–16S reference design (reference for measurement,
  protections and automotive-style layout decisions; its MOSFET stage is not
  adopted here): <https://www.ti.com/tool/TIDA-010208>
- EVE LF100LA Version A product-spec copy cited by the project model:
  <https://thebatteryshop.eu/shop_ordered/92904/pic/EVE_LF100_LA_datasheet.pdf>
  (third-party host; controlled source/lot revision still required).
- TI ISO1042-Q1 datasheet, reinforced/basic ordering variants and power data:
  <https://www.ti.com/lit/ds/symlink/iso1042-q1.pdf>
- TI UCC33421-Q1 isolated supply datasheet (5-V, 300-mA / 1.5-W capability):
  <https://www.ti.com/lit/ds/symlink/ucc33421-q1.pdf>
- ADI LTC3300-2 datasheet:
  <https://www.analog.com/media/en/technical-documentation/data-sheets/ltc3300-2.pdf>
- Wurth WE-FLYLT 750312504 datasheet:
  <https://www.we-online.com/components/products/datasheet/750312504.pdf>
- TI LM5164 wide-input buck candidate:
  <https://www.ti.com/product/LM5164>
- Espressif ESP32-S3-WROOM-1 module datasheet and TWAI interface:
  <https://documentation.espressif.com/esp32-s3-wroom-1_wroom-1u_datasheet_en.html>
- TI TPS1H200A-Q1 protected automotive high-side switch:
  <https://www.ti.com/product/TPS1H200A-Q1>
