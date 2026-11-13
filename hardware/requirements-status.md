# Hardware Design Checklist

Status: the AFE, protected auxiliary supply, MCU, sensing, reinforced isolated
CAN, USB protection, watchdog/fault-permit logic, smart contactor-coil drivers
and a 16-channel active-balancer candidate are captured in one hierarchical,
five-page schematic. Cross-sheet nets use global labels. KiCad 10.0.6 ERC with
`--severity-all` reports 0 errors and 0 warnings; the project still lists
single-use global labels, four-point joins, footprint-filter mismatches and
SPICE-model issues as excluded check classes. ERC is not a safety approval or
simulation. This is an assumption-based draft, not a fabrication release or
validated design.

## Decisions for the current non-PCB, non-simulation scope

These decisions bound the project without guessing at safety-critical ratings:

1. **USB service:** the connector is not galvanically isolated from BMS GND/VSS.
   Grounded USB service is prohibited while the pack is connected. A hardware
   isolation redesign for live-pack service is deferred and is not claimed.
2. **Active balancing:** the LTC3300-2 / Wurth transformer circuit remains a
   schematic study only. It is deferred from the build/procurement baseline and
   must not be populated unless the transformer is approved for the intended
   use or replaced and the power stage is independently reviewed.
3. **External high-voltage power stage:** contactors, fuse, shunt, cables and
   precharge resistor remain application-selected external equipment. Example
   values are not selections or authorization to connect a pack.
4. **IMD and HVIL:** only software abstractions are in scope. Physical IMD/HVIL
   circuits and vehicle integration are not implemented or claimed.
5. **PCB and physical validation:** PCB routing/DRC, fabrication, battery hookup,
   bench testing and vehicle qualification are outside the current request.

The project is therefore a documentation/software/schematic portfolio package,
not a hardware build package. No battery connection or component procurement
is authorized by these decisions.

| Plan task | Status | Evidence / remaining work |
|---|---|---|
| ELE-001 — VC0–VC16 mapping | Draft captured | 18-circuit keyed Molex Micro-Fit 3.0 connector candidate carries VC0–VC16 with one spare, plus 17 series filters and 16 differential capacitors. Confirm the mating harness pin numbering, cell-tap fusing and insulation against the pack drawing. |
| ELE-002 — BQ76952 supply/filter | Draft captured | BQ76952 BAT path, REG18 decoupling, 20-ohm/220-nF cell filters, thermistors and current sense are captured. PACK is connected to stack positive through 10 kΩ, LD is grounded for the no-high-side-FET design, and BREG has a 10-MΩ VSS path. REGIN is NC with REG0/REG1/REG2 intended disabled; verify the final configuration against TI’s controlled reference before release. |
| ELE-003 — current sense | Draft captured | Kelvin input, symmetric 100-ohm resistors and 100-nF differential filter are captured. Select the shunt and verify polarity, pulse/thermal limits, configuration and calibration. |
| ELE-004 — thermistors | Draft captured | Three external 10-kohm NTC inputs with filters and one board NTC divider are captured. The selected NTC curve, temperature conversion, placement, insulation and open/short diagnostics remain unverified. |
| ELE-005 — disconnect/precharge control | Control logic captured; external power stage intentionally unselected | Three SN74LVC1G08-Q1 gates condition MCU requests with `BMS_PERMIT`; a TPS3808-Q1 monitors BQ REG18 and a TPS3430-Q1 monitors heartbeat. The cross-coupled NAND latch captures the TPS3430 timed WDO pulse and defaults to inhibit at startup; firmware must pulse `WD_REARM_N` only after a healthy heartbeat. The 10-kΩ CWD / SET0=SET1=0 setup has a 10.35–92.7-ms guaranteed WDI window and the 20-Hz target fits. Configure BQ ALERT active-low. The 2-A current limit and 0.2-s latch-off remain provisional; no coil, contactor or external power-stage part is selected. |
| ELE-006 — MCU/CAN and service boundary | Circuit captured; USB restriction set for current scope | ESP32-S3, 3.3-V and 5-V rails, reinforced ISO1042DWRQ1, UCC33421-Q1 isolated supply, ESD2CAN24-Q1 CAN protection, USB-C protection, load-side divider with ADC clamps and board NTC are captured. USB GND/shield is tied to BMS GND/VSS. Grounded USB service is prohibited while the pack is connected; live-pack USB isolation redesign is deferred. The 100-mA / 0.5-W isolated-load budget is provisional against the UCC33421-Q1 5-V, 300-mA / 1.5-W capability; confirm actual load, layout, transients and orderable variants before release. |
| ELE-007 — ERC | Verified for draft | `kicad/integrated_erc.txt`: 0 errors and 0 warnings on the hierarchical root. The report lists ignored check classes, including SPICE-model issues. KiCad project-local `Power` and TI symbol libraries are configured. ERC does not approve electrical safety, component selection, or circuit behavior. |
| ELE-008 — footprints/constraints | Partial; active balancing deferred | Assigned footprint identifiers resolve. The 750312504 transformer symbol uses its actual terminal numbers and common-terminal pairs, but intentionally has no footprint. The active-balancer candidate is not in the build/procurement baseline. Verify every footprint/pin map against controlled orderable datasheets before any future release. |
| ELE-009 — PCB route/DRC | Out of current scope; placement draft exists | `kicad/intelligent_16s_bms.kicad_pcb` contains imported footprints but no routed copper, vias, zones or DRC evidence. PCB layout is excluded from this revision; no manufacturability claim is made. |
| ELE-010 — release outputs | Partial; design-only package | The five-page schematic PDF, netlist and draft BOM are generated from the hierarchical root. Exact-part sourcing, any future PCB package and independent electrical review are not complete. |

## Open gates if hardware integration is resumed

These are deliberately not resolved by inventing application data or part
ratings:

1. Verify the controlled LF100LA cell revision/lot and establish the actual
   charger, load, temperature and fault-current envelope before setting
   protection thresholds.
2. Select external contactors, fuse, shunt, cables and precharge components
   from the real continuous/pulse/fault current, DC-link capacitance, coil data
   and interruption requirements. The 50-A/100-A project target and example
   precharge values are not component selections.
3. Verify BQ76952 configuration, including active-low ALERT, cell-tap order,
   protection settings, thermistor curve/diagnostics and the watchdog/latch/
   rearm behavior against controlled datasheets and firmware.
4. Confirm orderable variants, connector/harness compatibility, power-supply
   transient/thermal margins and isolation requirements. Grounded USB remains
   prohibited while the pack is connected.
5. Keep the active-balancer candidate unpopulated unless the transformer is
   approved for intended use or replaced; then review its complete power stage,
   harness protection, thermal behavior and fail-safe behavior.
6. Physical IMD/HVIL, PCB layout/DRC, fabrication, battery hookup and vehicle
   qualification are outside the current scope and remain necessary for any
   future hardware-release claim.

No hardware fabrication, battery connection, physical validation,
certification or vehicle qualification is included or claimed.
