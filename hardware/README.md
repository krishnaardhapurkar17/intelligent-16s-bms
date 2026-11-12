# Hardware workspace

The hardware design is a control-board schematic draft. Pack current remains
off-board through external contactors, fuse, shunt and precharge components.
No board is being fabricated or physically tested.

## Integrated CAD

- [Integrated KiCad schematic](kicad/intelligent_16s_bms.kicad_sch)
- [Integrated schematic PDF](schematic-pdf/intelligent_16s_bms_system.pdf)
- [Integrated ERC report](kicad/integrated_erc.txt)
- [Integrated netlist](kicad/intelligent_16s_bms.net)
- [Draft BOM](bom/intelligent_16s_bms_draft.csv)
- [Design checklist](requirements-status.md)
- [Circuit definition and release gates](circuit-definition.md)

The source-page generators are in `tools/generate_afe_schematic.py`,
`tools/generate_controller_schematic.py`, `tools/generate_power_schematic.py`
and `tools/generate_balancer_schematic.py`. Recreate the project entry sheet
with `tools/merge_hardware_schematic.py` after regenerating the child sheets.
The root schematic is intentionally a single project sheet with separate child
sheets for AFE, controller, power/auxiliary logic and active balancing, instead
of one giant flat capture. The root plus four child sheets make a five-page
project. The sheets use global labels for cross-sheet nets and distinct
reference ranges for the controller, auxiliary-power and active-balancer pages.

From the repository root, regenerate the design and project-local symbol
library with:

```powershell
python .\tools\generate_afe_schematic.py
python .\tools\generate_controller_schematic.py
python .\tools\generate_power_schematic.py
python .\tools\generate_balancer_schematic.py
python .\tools\merge_hardware_schematic.py
python .\tools\export_kicad_custom_library.py
```

KiCad 10.0.6 ERC on the top-level, five-page schematic reports zero errors and
zero warnings after regeneration. The report lists ignored check classes,
including SPICE-model issues. ERC checks schematic rules only; it is not
electrical design approval, circuit simulation, or DRC.

The KiCad PCB file currently contains imported footprints but no routed copper,
vias, zones, or DRC evidence. It is an unrouted placement draft, not a completed
layout. The active-balancer schematic is an LTC3300-2-family draft with a
16-channel transformer stage. The Wurth transformer candidate is not approved
for transportation use without manufacturer agreement, and its PCB footprint
is intentionally unassigned. Contactor coil settings remain provisional;
cell-specific configuration, external contactor/fuse/precharge selection, PCB
placement/routing, DRC and independent review remain open. Do not connect a
battery to this unvalidated draft.

The idealized software precharge study is reproducible with
`tools/run_precharge_assumption_sim.py`; it is not a KiCad SPICE run or
component-model validation. Circuit-level KiCad simulation remains open.

The software state-machine behavior is described in
`docs/bdu-state-machine.md`; project status and limitations are summarized in
`docs/portfolio-evidence-register.md`.
