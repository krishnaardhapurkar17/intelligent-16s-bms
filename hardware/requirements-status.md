# Hardware Design Checklist

Status: the AFE, protected auxiliary supply, MCU, sensing, reinforced isolated
CAN, USB protection, watchdog/fault-permit logic, smart contactor-coil drivers
and a 16-channel active-balancer candidate are captured in one hierarchical,
five-page schematic. Cross-sheet nets use global labels. the latest KiCad
10.0.6 ERC reports 0 errors and 0 warnings; its report ignores single-use
global labels, four-point joins, footprint-filter mismatches and SPICE-model
issues. Review each exclusion before relying on the result. This is an
assumption-based draft, not a fabrication release, electrical safety approval
or validated design.

| Plan task | Status | Evidence / remaining work |
|---|---|---|
| ELE-001 — VC0–VC16 mapping | Draft captured | 18-circuit keyed Molex Micro-Fit 3.0 connector candidate carries VC0–VC16 with one spare, plus 17 series filters and 16 differential capacitors. Confirm the mating harness pin numbering, cell-tap fusing and insulation against the pack drawing. |
| ELE-002 — BQ76952 supply/filter | Draft captured | BQ76952 BAT path, REG18 decoupling, 20-ohm/220-nF cell filters, thermistors and current sense are captured. PACK is connected to stack positive through 10 kΩ, LD is grounded for the no-high-side-FET design, and BREG has a 10-MΩ VSS path. REGIN is NC with REG0/REG1/REG2 intended disabled; verify the final configuration against TI’s controlled reference before release. |
| ELE-003 — current sense | Draft captured | Kelvin input, symmetric 100-ohm resistors and 100-nF differential filter are captured. Select the shunt and verify polarity, pulse/thermal limits, configuration and calibration. |
| ELE-004 — thermistors | Draft captured | Three external 10-kohm NTC inputs with filters and one board NTC divider are captured. The selected NTC curve, temperature conversion, placement, insulation and open/short diagnostics remain unverified. |
| ELE-005 — disconnect/precharge control | Circuit draft captured; actual coils and external power stage open | Three SN74LVC1G08-Q1 gates condition MCU requests with `BMS_PERMIT`; a TPS3808-Q1 monitors BQ REG18 and a TPS3430-Q1 monitors heartbeat. The cross-coupled NAND latch captures the TPS3430 timed WDO pulse and defaults to inhibit at startup; firmware must pulse `WD_REARM_N` only after a healthy heartbeat. The 10-kΩ CWD / SET0=SET1=0 setup has a 10.35–92.7-ms guaranteed WDI window and the 20-Hz target fits. Configure BQ ALERT active-low. The 2-A current limit and 0.2-s latch-off remain provisional until coil pull-in/hold and thermal data are known. |
| ELE-006 — MCU/CAN | Circuit draft captured; electrical and isolation validation open | ESP32-S3, 3.3-V and 5-V rails, reinforced ISO1042DWRQ1, UCC33421-Q1 isolated supply, ESD2CAN24-Q1 CAN protection, USB-C protection, load-side divider with ADC clamps and board NTC are captured. USB GND/shield is tied to BMS GND/VSS, so the service port is not isolated from the pack-referenced domain; use an approved isolated interface or disconnect the pack before grounded service. A 100-mA / 0.5-W isolated-load budget is reserved against the UCC33421-Q1 5-V, 300-mA / 1.5-W capability; confirm the worst-case ISO1042, termination and auxiliary load. Validate isolation layout, bus/shield strategy, transients and orderable variants. |
| ELE-007 — ERC | Verified for draft | `kicad/integrated_erc.txt`: 0 errors and 0 warnings on the hierarchical root. The report lists ignored check classes, including SPICE-model issues. KiCad project-local `Power` and TI symbol libraries are configured. ERC does not approve electrical safety, component selection, or circuit behavior. |
| ELE-008 — footprints/constraints | Partial | Assigned footprint identifiers resolve. The 750312504 transformer schematic symbol now uses its actual terminal numbers and common-terminal pairs, but intentionally has no footprint pending PCB-owner package review. Verify every footprint/pin map against controlled orderable datasheets, then define stackup, isolation/creepage, RF keepout, thermal and placement constraints during PCB work. |
| ELE-009 — PCB route/DRC | Not started; placement draft exists | `kicad/intelligent_16s_bms.kicad_pcb` contains imported footprints, but no routed copper, vias, zones, or DRC evidence was found. Placement constraints, routing and manufacturing outputs remain out of scope for this revision. |
| ELE-010 — release outputs | Partial | Five-page schematic PDF, netlist and draft BOM are regenerated from the hierarchical root. Exact-part sourcing, PCB layout, DRC, manufacturing package and independent electrical review remain. |

## Remaining engineering work

1. Select the actual main/precharge contactors and confirm coil voltage,
   pull-in/hold current, inductive energy, auxiliary-contact behavior and
   thermal conditions. The captured 2-A current limit / 0.2-s latch-off is a
   candidate envelope, not a verified match to any selected coil.
2. Verify the 10-A auxiliary fuse, SM8S33A TVS, LM74700-Q1, BUK9Y22-100E and
   both LM5164-Q1 channels against the real vehicle transient/load profile,
   surge energy, inrush and thermal limits. Confirm the UCC33421-Q1 load budget
   and reinforced-isolation layout; the present 100-mA isolated-load budget is
   provisional.
3. Confirm the controlled LF100LA cell revision and limits, current and
   temperature envelope, shunt, prospective fault current, pack fuse/contactor
   coordination, DC-link capacitance and precharge resistor/timing.
4. Configure BQ76952 ALERT active-low. Verify the TPS3430-Q1 window, heartbeat
   timing, startup fault latch, firmware rearm pulse and exact watchdog
   configuration. The latch is now captured in hardware; its reset/rearm and
   full safety behavior have not been independently reviewed.
5. Confirm exact orderable variants and mating harness parts, verify every
   symbol-to-package pin map and PCB footprint, and complete an independent
   electrical review. The active-balancer transformer has no assigned
   footprint yet; the selected Wurth datasheet also excludes transportation
   applications absent manufacturer approval.
6. Active balancing is captured as a draft: three LTC3300-2 devices, 16
   transformer channels, isolated SPI/permit and per-device watchdog pause.
   The separate J30 balance harness must connect at the same pack-side cell
   nodes as J1 while keeping balancing current out of the AFE sense harness.
   The intended policy is charge-only, closed BDU, valid sensors, no fault,
   below 45 C, with only one channel enabled at a time. Verify the 16S mapping,
   controller qualification, transformer suitability, MOSFET/sense ratings,
   1-A transfer target, harness ampacity/fusing, snubbers, thermal behavior,
   cell-temperature sensing and fail-safe response before any release.
7. PCB-owner tasks: complete placement and routing, assign the transformer
   footprint, run DRC, and prepare manufacturing outputs. The current PCB file
   is an unrouted placement draft. No board fabrication or physical validation
   is claimed here.
8. Resolve the non-isolated USB service path before connecting a grounded host
   to an energized pack-referenced BMS. Add a galvanically isolated service
   interface or approve a documented service procedure that disconnects the
   pack; do not treat USB ESD protection as galvanic isolation.

No hardware fabrication, battery connection, physical validation,
certification or vehicle qualification is included or claimed.
