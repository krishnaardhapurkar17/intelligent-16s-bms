import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { Workbook, SpreadsheetFile } = require('@oai/artifact-tool');

const outputDir = import.meta.dirname;
const root = path.resolve(outputDir, '..', '..');
const input = JSON.parse(await fs.readFile(path.join(root, '.tmp', 'tracker_tasks.json'), 'utf8'));
const audited = input['Intelligent_BMS_Project_Tracker_Audited.xlsx'];
const upgrade = input['Intelligent_BMS_Project_Tracker_Simulation_Upgrade.xlsx'];
const byId = new Map(upgrade.map(row => [row['Task ID'], row]));

const verified = (evidence, next = 'Keep evidence linked; rerun the applicable check after changes.') =>
  ({ status: 'Evidence verified', evidence, next });
const partial = (evidence, next) => ({ status: 'Implemented with open evidence', evidence, next });
const open = (evidence, next) => ({ status: 'Open plan item', evidence, next });
const deferred = (evidence, next) => ({ status: 'Deferred from current scope', evidence, next });

const decisions = {
  'GOV-001': partial('Intelligent_BMS_Word_Documents/01_Project_Charter.docx; docs/source-document-audit.md', 'Project owner sign-off is still needed; content review alone is not approval.'),
  'GOV-002': partial('Intelligent_BMS_Word_Documents/02_System_Requirements_Specification.docx; docs/requirements-traceability-matrix.md', 'Approve the requirement baseline and resolve TBD operating-envelope criteria.'),
  'GOV-003': verified('docs/requirements-traceability-matrix.md; tests/regression/validate_traceability.py; results/regression/traceability_validation.json'),
  'GOV-004': verified('docs/decision-log.md (ADR-001 through ADR-009)'),
  'GOV-005': partial('docs/assumptions-register.md; docs/source-document-audit.md', 'Convert the reviewed risks into a controlled, scored risk register after the project owner approves a scoring method.'),
  'GOV-006': verified('Git repository initialized; main tracks origin/main; README.md', 'Keep future project changes committed and pushed; preserve the dataset exclusion.'),
  'REQ-001': partial('docs/decision-log.md (ADR-001); docs/assumptions-register.md', 'Confirm the target commercial cell and validate parameter applicability; current ECM choice remains provisional.'),
  'REQ-002': open('SRS operating-envelope values remain TBD.', 'Set justified voltage, current, temperature, SOC and load limits for the target cell/pack.'),
  'REQ-003': verified('docs/requirements-traceability-matrix.md; SIM-001 to SIM-020 coverage'),
  'REQ-004': open('The SRS and V&V plan retain TBD numerical acceptance targets.', 'Approve acceptance criteria only after the operating envelope and baseline are justified.'),
  'REQ-005': partial('Intelligent_BMS_Word_Documents/04_Verification_and_Validation_Plan.docx; tests/regression/run_regression.py', 'Approve the plan and add requirement-specific numerical thresholds where the project baseline supports them.'),
  'ARC-001': partial('Intelligent_BMS_Word_Documents/03_System_Architecture_and_Design.docx; docs/software-interface-boundaries.md', 'Architecture is documented; a formal freeze/sign-off is pending.'),
  'ARC-002': verified('docs/software-interface-boundaries.md; software/interfaces/message_schema.py; tests/unit/test_project_interfaces_and_lifecycle.py'),
  'ARC-003': partial('docs/decision-log.md (ADR-003); results/metrics/lfp_16s_active_passive_balancing.json', 'Software trade study is complete; select a component-level topology only in the later PCB design phase.'),
  'ARC-004': verified('docs/software-interface-boundaries.md; software/diagnostics/lfp_16s_supervisory_controller.py; tests/unit/test_lfp_16s_bdu_independence.py'),
  'ARC-005': open('software/interfaces/message_schema.py defines transport-independent messages but no CAN identifier/bit timing map.', 'Define the CAN signal/identifier map during the later hardware integration phase.'),
  'BAT-001': verified('environment/requirements-core.txt; docs/clean-environment-verification.md'),
  'BAT-002': verified('environment/requirements-core.txt; models/pack-model/single_cell_discharge.py; results/regression/regression_report.json'),
  'BAT-003': partial('docs/decision-log.md (ADR-001); results/metrics/lf100la_identified_parameters.json', 'Reference chemistry and ECM settings are documented; validate the target cell parameter set.'),
  'BAT-004': verified('models/pack-model/single_cell_discharge.py; results/metrics/single_cell_discharge.csv'),
  'BAT-005': verified('models/pack-model/lfp_16s_pack_simulation.py; results/metrics/lfp_16s_pack_baseline.csv'),
  'BAT-006': verified('models/pack-model/cell_configuration.py; results/metrics/lfp_16s_weak_cell.csv'),
  'BAT-007': verified('models/pack-model/lfp_16s_pack_simulation.py; multiple profile and load scenario scripts'),
  'BAT-008': verified('models/pack-model/lfp_16s_temperature_diagnostic.py; results/metrics/lfp_16s_temperature_summary.json'),
  'BAT-009': verified('results/metrics/lfp_16s_pack_baseline.csv; results/regression/regression_summary.txt'),
  'BAS-001': verified('software/diagnostics/lfp_16s_sensor_safety_gate.py; software/interfaces/message_schema.py'),
  'BAS-002': verified('models/pack-model/lfp_16s_sensor_bias_test.py; models/pack-model/lfp_16s_robustness_test.py'),
  'BAS-003': verified('software/diagnostics/lfp_voltage_baseline.py; tests/unit/test_lfp_voltage_baseline.py'),
  'BAS-004': verified('models/pack-model/lfp_16s_soc_estimator.py; models/pack-model/lfp_16s_ocv_soc_fusion.py'),
  'BAS-005': verified('tests/regression/run_regression.py; tests/regression/expected_artifacts.json'),
  'BAS-006': verified('tests/unit/; tests/regression/regression_summary.txt'),
  'DIA-001': verified('software/diagnostics/lfp_voltage_baseline.py; models/pack-model/lfp_16s_combined_fault_diagnostic.py'),
  'DIA-002': partial('models/pack-model/lfp_16s_fault_isolation_test.py; tools/evaluate_fault_diagnostic_grid.py', 'Synthetic residual and pulse response checks exist; validate thresholds against independent measured trajectories.'),
  'DIA-003': verified('models/pack-model/lfp_16s_combined_fault_diagnostic.py; results/metrics/lfp_16s_combined_fault_summary.json'),
  'DIA-004': verified('results/metrics/lfp_fault_baseline_comparison.json; results/metrics/lfp_fault_diagnostic_grid.json'),
  'DIA-005': partial('results/metrics/lfp_fault_diagnostic_grid.json; results/metrics/lfp_16s_combined_fault_summary.json', '339 seeded synthetic cases now cover 16 locations and multiple severities; add an external measured or independently generated holdout.'),
  'BAL-001': partial('docs/decision-log.md (ADR-003); results/metrics/lfp_16s_active_passive_balancing.json', 'Behavioral comparison is complete; hardware-specific switch/capacitor choice is deferred.'),
  'BAL-002': verified('models/balancing/lfp_16s_passive_balancing.py; models/balancing/lfp_16s_switched_cap_active_balancing.py'),
  'BAL-003': verified('models/balancing/lfp_16s_passive_balancing.py; models/balancing/lfp_16s_switched_cap_active_balancing.py; tests/unit/test_lfp_16s_switched_cap_balancing.py'),
  'BAL-004': verified('results/metrics/lfp_16s_passive_balancing_summary.json; results/metrics/lfp_16s_active_passive_balancing.json'),
  'BAL-005': verified('results/metrics/lfp_16s_active_passive_balancing.json'),
  'AI-001': verified('models/ai/README.md; models/ai/'),
  'AI-002': verified('docs/source-document-audit.md; models/ai/README.md; tools/prepare_lfp_dataset.py'),
  'AI-003': partial('models/ai/soc_evaluation_results.csv; tests/unit/test_ai_model_integration.py; docs/decision-log.md (ADR-004)', 'Supplied SOC CNN-LSTM passes held-out NMC validation; no LFP SOC AI is enabled because current datasets lack suitable multi-cell temperature-aware reference coverage.'),
  'AI-004': partial('results/metrics/lfp_ai_validation.json; results/metrics/lfp_ai_protocol_group_validation.json', 'SOH research model evaluated on current holdouts; review worst-case error against approved acceptance limits.'),
  'AI-005': partial('results/metrics/lfp_rul_group_cross_validation.json; results/metrics/lfp_rul_external_pack_validation.json; results/metrics/lfp_rul_baseline_comparison.json; docs/decision-log.md (ADR-005)', 'Reduced model improves MAE. The separate external dataset covers one pack and uses dataset-endpoint labels; obtain independent measured end-of-life data across multiple packs and approve an error criterion.'),
  'AI-006': verified('software/estimation/ai_battery_estimators.py; tests/unit/test_ai_model_integration.py'),
  'AI-007': partial('results/metrics/ai_inference_profile.json', 'Desktop profiling includes SOC CNN-LSTM; embedded/Raspberry Pi performance is unmeasured.'),
  'AI-008': open('Diagnostic CSV/JSON reports exist; no user-facing dashboard implementation was found.', 'Build a dashboard only if it is part of the intended software deliverable.'),
  'VER-001': verified('docs/requirements-traceability-matrix.md; results/regression/traceability_validation.json'),
  'VER-002': verified('results/regression/regression_summary.txt (latest full run passed)'),
  'VER-003': open('Numerical acceptance criteria are still TBD in the baseline documents.', 'Set an approved operating envelope and acceptance thresholds before declaring accuracy acceptance.'),
  'VER-004': verified('docs/assumptions-register.md; docs/software-interface-boundaries.md; models/ai/README.md'),
  'VER-005': open('No signed engineering design review record was identified.', 'Record a project-owner design review after open requirements and acceptance criteria are resolved.'),
  'PUB-001': verified('README.md'),
  'PUB-002': partial('.gitignore; source provenance and licensing review is not complete.', 'Review licenses for all supplied model/data assets and prepare a clean distributable repository.'),
  'PUB-003': partial('results/figures/; docs/plot-review-record.md', 'Plots are generated and selected plots reviewed; package a curated demo set if publication is planned.'),
  'PUB-004': open('GitHub repository and origin/main are present; no tagged GitHub Release exists, and current working changes are not committed.', 'Create a versioned release only after project review, dataset/license checks, and owner approval.'),
  'PUB-005': open('No social post was made.', 'Draft and publish only if requested by the project owner.'),
  'AUTO-001': verified('docs/software-interface-boundaries.md; docs/assumptions-register.md'),
  'AUTO-002': verified('docs/software-interface-boundaries.md; software/pmu/lfp_16s_state_of_power.py; software/protection/lfp_16s_state_of_safety.py'),
  'AUTO-003': verified('software/protection/lfp_16s_protection_bdu.py; tests/unit/test_lfp_16s_protection_bdu_unit.py'),
  'AUTO-004': verified('docs/software-interface-boundaries.md; software/diagnostics/lfp_16s_supervisory_controller.py'),
  'AUTO-005': verified('software/lifecycle/battery_passport.py; software/interfaces/command_authorization.py; software/interfaces/message_schema.py'),
  'AUTO-006': verified('tests/regression/regression_summary.txt; subsystem scenario coverage across PMU/BDU/IMU/TMU/diagnostics/balancing'),
};

const hardwareDecisions = {
  'ELE-001': partial('hardware/requirements-status.md; hardware/kicad/afe_16s.kicad_sch', 'Confirm connector pin numbering, mating harness, cell-tap protection and insulation against controlled pack drawings.'),
  'ELE-002': partial('hardware/requirements-status.md; hardware/kicad/afe_16s.kicad_sch', 'Review the complete BQ76952 supply and cell-input circuit against TI’s controlled reference and final configuration.'),
  'ELE-003': partial('hardware/requirements-status.md; hardware/circuit-definition.md', 'Select the external shunt from the actual current/fault envelope; verify thermal limits, polarity, calibration and protection settings.'),
  'ELE-004': partial('hardware/requirements-status.md; hardware/circuit-definition.md', 'Select the NTC curve and verify placement, insulation, conversion and open/short diagnostics against the target cell.'),
  'ELE-005': partial('hardware/design-basis.md; hardware/requirements-status.md; hardware/kicad/controller_16s.kicad_sch', 'This architecture uses external contactors, not a BQ high-side MOSFET disconnect path. Verify BQ protection alert/latch behavior and the external coil drivers; configure ALERT active-low. Contactors and power-stage ratings remain unselected.'),
  'ELE-006': partial('hardware/requirements-status.md; hardware/kicad/controller_16s.kicad_sch; docs/decision-log.md (ADR-007)', 'Current schematic uses ESP32-S3 TWAI with isolated CAN, not an MCP2515. Review the intended interface, isolation/layout and orderable variants; grounded USB service is prohibited while the pack is connected.'),
  'ELE-007': partial('hardware/kicad/integrated_erc.txt; hardware/requirements-status.md', 'ERC reports 0 errors/warnings with --severity-all; four check classes remain excluded. Review/justify exclusions before any hardware release.'),
  'ELE-008': deferred('hardware/requirements-status.md; hardware/kicad/intelligent_16s_bms.kicad_pcb', 'PCB footprints, stackup and placement/clearance constraints are deferred. The active-balancer transformer has no footprint and is not in the build baseline.'),
  'ELE-009': deferred('hardware/requirements-status.md; hardware/kicad/intelligent_16s_bms.kicad_pcb', 'PCB routing and DRC are outside this revision; no routed copper or DRC result is claimed.'),
  'ELE-010': partial('hardware/schematic-pdf/intelligent_16s_bms_system.pdf; hardware/kicad/integrated_erc.txt; hardware/bom/README.md', 'Schematic PDF/ERC are current; BOM remains non-procurement draft. Exact-part approval, PCB/manufacturing outputs and independent release review remain open.'),
};
const getDecision = row => {
  const id = row['Task ID'];
  if (hardwareDecisions[id]) return hardwareDecisions[id];
  return decisions[id] || open('No qualifying evidence was mapped from the current repository.', 'Review the task definition and attach specific repository evidence before changing its status.');
};

const wb = Workbook.create();
const summary = wb.worksheets.add('Status Summary');
const tasks = wb.worksheets.add('Task Reconciliation');

const rows = audited.map(a => {
  const u = byId.get(a['Task ID']) || {};
  const d = getDecision(a);
  return [a['Task ID'], a.Phase, a.Task,
    a.Status || '', u.Status || '', d.status, d.evidence, d.next];
});

summary.getRange('A1:H1').merge();
summary.getRange('A1').values = [['Intelligent BMS — Evidence-Based Tracker Reconciliation']];
summary.getRange('A2:H2').merge();
summary.getRange('A2').values = [['Assessment date: 13 Nov 2026 | Original tracker statuses are retained in column N of the updated source workbooks.']];
summary.getRange('A4:B4').values = [['Assessment outcome', 'Task count']];
const categories = ['Evidence verified', 'Implemented with open evidence', 'Open plan item', 'Deferred from current scope'];
summary.getRange(`A5:A${4 + categories.length}`).values = categories.map(x => [x]);
summary.getRange(`B5:B${4 + categories.length}`).formulas = categories.map((_, i) => [`=COUNTIF('Task Reconciliation'!F:F,A${5 + i})`]);
summary.getRange('D4:H4').merge();
summary.getRange('D4').values = [['How to read this reconciliation']];
summary.getRange('D5:H8').merge(true);
summary.getRange('D5:D8').values = [
  ['Evidence verified: repository artifact and/or test evidence exists for the task definition.'],
  ['Implemented with open evidence: relevant work exists, but scope approval, target-cell validation, or external evidence is still missing.'],
  ['Open plan item: no qualifying implementation/approval evidence was found, or a required decision remains unresolved.'],
  ['Deferred from current scope: explicitly excluded from this revision; not complete.'],
];
summary.getRange('A10:H10').merge();
summary.getRange('A10').values = [['Do not mark a project-plan item complete from its tracker entry alone. Review the evidence and action columns in Task Reconciliation.']];

tasks.getRange('A1:H1').values = [[
  'Task ID','Phase','Task','Audited tracker status','Simulation upgrade status',
  'Reconciled assessment','Repository evidence reviewed','Next action / limitation'
]];
if (rows.length) tasks.getRange(`A2:H${rows.length + 1}`).values = rows;

summary.getRange('A1:H1').format = { fill: '#16324F', font: { name: 'Aptos Display', size: 16, bold: true, color: '#FFFFFF' }, rowHeight: 34 };
summary.getRange('A2:H2').format = { fill: '#DCE6F1', font: { name: 'Aptos', size: 10, color: '#203040' }, rowHeight: 30, wrapText: true };
summary.getRange('A4:B4').format = { fill: '#2F6690', font: { name: 'Aptos', bold: true, color: '#FFFFFF' } };
summary.getRange('D4:H4').format = { fill: '#2F6690', font: { name: 'Aptos', bold: true, color: '#FFFFFF' } };
summary.getRange(`A5:B${4 + categories.length}`).format = { fill: '#EEF3F8', font: { name: 'Aptos', size: 11 } };
summary.getRange('D5:H8').format = { wrapText: true, verticalAlignment: 'center', font: { name: 'Aptos', size: 10 } };
summary.getRange('A10:H10').format = { fill: '#FFF2CC', font: { name: 'Aptos', size: 10, bold: true }, wrapText: true, rowHeight: 32 };
summary.getRange('A:A').format.columnWidth = 38;
summary.getRange('B:B').format.columnWidth = 15;
summary.getRange('C:C').format.columnWidth = 3;
summary.getRange('D:H').format.columnWidth = 18;

tasks.getRange('A1:H1').format = { fill: '#16324F', font: { name: 'Aptos', size: 10, bold: true, color: '#FFFFFF' }, wrapText: true, rowHeight: 34, verticalAlignment: 'center' };
tasks.getRange(`A2:H${rows.length + 1}`).format = { font: { name: 'Aptos', size: 9 }, wrapText: true, verticalAlignment: 'top' };
tasks.getRange(`A2:B${rows.length + 1}`).format.fill = '#F2F6FA';
tasks.getRange(`A2:A${rows.length + 1}`).format.font = { name: 'Aptos', size: 9, bold: true, color: '#16324F' };
tasks.getRange('A:A').format.columnWidth = 13;
tasks.getRange('B:B').format.columnWidth = 19;
tasks.getRange('C:C').format.columnWidth = 34;
tasks.getRange('D:E').format.columnWidth = 21;
tasks.getRange('F:F').format.columnWidth = 30;
tasks.getRange('G:G').format.columnWidth = 50;
tasks.getRange('H:H').format.columnWidth = 58;
tasks.getRange(`A2:H${rows.length + 1}`).format.rowHeight = 78;
tasks.freezePanes.freezeRows(1);

wb.recalculate();
const preview = await wb.render({ sheetName: 'Status Summary', range: 'A1:H10', scale: 1, format: 'png' });
await fs.writeFile(path.join(outputDir, 'tracker_summary_preview.png'), new Uint8Array(await preview.arrayBuffer()));
const detailPreview = await wb.render({ sheetName: 'Task Reconciliation', range: 'A1:H14', scale: 1, format: 'png' });
await fs.writeFile(path.join(outputDir, 'tracker_detail_preview.png'), new Uint8Array(await detailPreview.arrayBuffer()));
const output = await SpreadsheetFile.exportXlsx(wb);
await output.save(path.join(outputDir, 'project_tracker_reconciliation.xlsx'));
console.log(JSON.stringify({ rows: rows.length, output: path.join(outputDir, 'project_tracker_reconciliation.xlsx') }));
