import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from software.diagnostics.lfp_16s_sensor_safety_gate import (
    SensorQualityGate,
)
from software.diagnostics.lfp_16s_insulation_monitor import (
    InsulationMonitoringUnit,
)
from software.diagnostics.lfp_16s_thermal_management import (
    ThermalManagementUnit,
)

CELL_COUNT = 16

INPUT_FILE = (
    PROJECT_ROOT
    / "results"
    / "metrics"
    / "lfp_16s_unified_diagnostics.csv"
)

OUTPUT_CSV = (
    PROJECT_ROOT
    / "results"
    / "metrics"
    / "lfp_16s_supervisory_decisions.csv"
)

OUTPUT_JSON = (
    PROJECT_ROOT
    / "results"
    / "metrics"
    / "lfp_16s_supervisory_summary.json"
)


class SupervisoryController:

    def __init__(self):
        self.sensor_gate = SensorQualityGate()
        self.tmu = ThermalManagementUnit()

    def evaluate_context(
        self,
        context_df,
        cell_voltages,
        cell_temperatures,
        pack_current,
        bdu_state,
        protection_fault,
        charge_mode,
        suspect_voltage_cells=None,
        suspect_temperature_cells=None,
        current_sensor_suspect=False,
        insulation_state="NORMAL",
        insulation_measurement_quality="VALID",
    ):

        context_df = context_df.copy()

        # ----------------------------------------------------
        # Validate diagnostic context
        # ----------------------------------------------------

        if len(context_df) != CELL_COUNT:
            raise ValueError(
                f"Expected {CELL_COUNT} cell records."
            )

        if sorted(context_df["Cell"].tolist()) != list(
            range(1, CELL_COUNT + 1)
        ):
            raise ValueError(
                "Context must contain exactly one record "
                "for each cell."
            )

        # ----------------------------------------------------
        # Evaluate sensor quality
        # ----------------------------------------------------

        quality = self.sensor_gate.evaluate(
            cell_voltages=cell_voltages,
            cell_temperatures=cell_temperatures,
            pack_current=pack_current,
            suspect_voltage_cells=suspect_voltage_cells,
            suspect_temperature_cells=suspect_temperature_cells,
            current_sensor_suspect=current_sensor_suspect,
        )

        # ----------------------------------------------------
        # Thermal Management Unit assessment
        # ----------------------------------------------------

        thermal_reading = self.tmu.process_measurements(
            cell_temperatures_c=cell_temperatures,
            suspect_cells=suspect_temperature_cells,
        )

        thermal_monitoring_valid = (
            thermal_reading.measurement_quality == "VALID"
            and thermal_reading.thermal_state in {
                "NORMAL",
                "WARNING",
                "CRITICAL",
            }
        )

        thermal_balancing_eligible = (
            thermal_monitoring_valid
            and thermal_reading.thermal_state == "NORMAL"
        )

        # Expose thermal assessment through the existing
        # quality return dictionary without changing its API.
        quality["thermal_state"] = (
            thermal_reading.thermal_state
            if thermal_monitoring_valid
            else "UNKNOWN"
        )

        quality["thermal_measurement_quality"] = (
            thermal_reading.measurement_quality
        )

        quality["thermal_monitoring_valid"] = bool(
            thermal_monitoring_valid
        )

        quality["thermal_temperature_spread_c"] = (
            thermal_reading.temperature_spread_c
        )

        quality["thermal_hottest_cell"] = (
            thermal_reading.hottest_cell
        )

        quality["thermal_hottest_temperature_c"] = (
            thermal_reading.hottest_temperature_c
        )

        quality["thermal_charge_derating_recommended"] = (
            thermal_reading.charge_derating_recommended
        )

        quality["thermal_discharge_derating_recommended"] = (
            thermal_reading.discharge_derating_recommended
        )

        quality["thermal_balancing_interlock"] = (
            not thermal_balancing_eligible
        )

        quality["thermal_reasons"] = thermal_reading.reasons

        insulation_monitoring_valid = (
            insulation_measurement_quality == "VALID"
            and insulation_state in {
                "NORMAL",
                "WARNING",
                "CRITICAL",
            }
        )

        insulation_balancing_eligible = (
            insulation_monitoring_valid
            and insulation_state == "NORMAL"
        )

        # ----------------------------------------------------
        # Global balancing permission
        # ----------------------------------------------------

        global_balancing_enable = (
            bdu_state == "CLOSED"
            and not protection_fault
            and charge_mode
            and quality["global_balancing_eligible"]
            and insulation_balancing_eligible
            and thermal_balancing_eligible
        )

        decisions = []

        # ----------------------------------------------------
        # Per-cell supervisory decisions
        # ----------------------------------------------------

        for _, row in context_df.iterrows():

            cell = int(row["Cell"])
            index = cell - 1

            capacity_fault = bool(
                row["Capacity_Fault_Detected"]
            )

            resistance_fault = bool(
                row["Resistance_Fault_Detected"]
            )

            voltage_valid = bool(
                quality["voltage_valid"][index]
            )

            temperature_valid = bool(
                quality["temperature_valid"][index]
            )

            sensor_valid = (
                voltage_valid and temperature_valid
            )

            # Diagnostic classification
            if capacity_fault and resistance_fault:
                fault_class = "MULTIPLE_DEGRADATION_INDICATORS"

            elif capacity_fault:
                fault_class = "CAPACITY_DEGRADATION"

            elif resistance_fault:
                fault_class = "RESISTANCE_DEGRADATION"

            else:
                fault_class = "NO_THRESHOLD_BREACH"

            # Severity describes diagnostic degradation only.
            # It is not a hardware protection command.
            if capacity_fault and resistance_fault:
                severity = "MULTIPLE_INDICATORS"

            elif capacity_fault or resistance_fault:
                severity = "DEGRADATION_INDICATED"

            else:
                severity = "NO_DEGRADATION_THRESHOLD_BREACH"

            # Evidence category, not a calibrated probability.
            if capacity_fault or resistance_fault:
                evidence_grade = "ESTIMATOR_THRESHOLD_FLAG"

            else:
                evidence_grade = "NO_ESTIMATOR_THRESHOLD_FLAG"

            if not sensor_valid:
                sensor_status = "INVALID_OR_SUSPECT"

            else:
                sensor_status = "VALID"

            # Sensor validity and BDU state are independent
            # requirements for balancing.
            cell_balancing_eligible = (
                global_balancing_enable
                and sensor_valid
            )

            decisions.append({

                "SOH_Scenario": row["SOH_Scenario"],
                "RUL_Scenario": row["RUL_Scenario"],
                "SOC_Operating_Scenario":
                    row["SOC_Operating_Scenario"],

                "Cell": cell,

                "Estimated_SOC_percent":
                    float(row["Estimated_SOC_percent"]),

                "Estimated_Capacity_SOH_percent":
                    float(
                        row["Estimated_Capacity_SOH_percent"]
                    ),

                "Estimated_Resistance_Growth_percent":
                    float(
                        row[
                            "Estimated_Resistance_Growth_percent"
                        ]
                    ),

                "Capacity_RUL_cycles":
                    float(row["Capacity_RUL_cycles"]),

                "Resistance_RUL_cycles":
                    float(row["Resistance_RUL_cycles"]),

                "Estimated_Total_RUL_cycles":
                    float(row["Estimated_Total_RUL_cycles"]),

                "Limiting_Mechanism":
                    row["Limiting_Mechanism"],

                "Capacity_Fault_Detected":
                    capacity_fault,

                "Resistance_Fault_Detected":
                    resistance_fault,

                "Fault_Classification":
                    fault_class,

                "Diagnostic_Severity":
                    severity,

                "Evidence_Grade":
                    evidence_grade,

                "Voltage_Sensor_Valid":
                    voltage_valid,

                "Temperature_Sensor_Valid":
                    temperature_valid,

                "Sensor_Status":
                    sensor_status,

                "BDU_State":
                    bdu_state,

                "Protection_Fault":
                    bool(protection_fault),

                "Balancing_Eligible":
                    bool(cell_balancing_eligible),

                "AI_Role":
                    "ADVISORY_ONLY",

                "Protection_Authority":
                    "BDU_ONLY",
                                "Insulation_State": (
                    insulation_state
                    if insulation_monitoring_valid
                    else "UNKNOWN"
                ),

                "Insulation_Measurement_Quality":
                    insulation_measurement_quality,

                "Insulation_Monitoring_Valid":
                    bool(insulation_monitoring_valid),

                "Insulation_Balancing_Interlock":
                    bool(not insulation_balancing_eligible),
                "Thermal_State": quality["thermal_state"],

                "Thermal_Measurement_Quality":
                    quality["thermal_measurement_quality"],

                "Thermal_Monitoring_Valid":
                    quality["thermal_monitoring_valid"],

                "Thermal_Temperature_Spread_C":
                    quality["thermal_temperature_spread_c"],

                "Thermal_Hottest_Cell":
                    quality["thermal_hottest_cell"],

                "Thermal_Hottest_Temperature_C":
                    quality["thermal_hottest_temperature_c"],

                "Charge_Derating_Recommended":
                    quality["thermal_charge_derating_recommended"],

                "Discharge_Derating_Recommended":
                    quality["thermal_discharge_derating_recommended"],

                "Thermal_Balancing_Interlock":
                    quality["thermal_balancing_interlock"],

                "Thermal_Reasons":
                    ";".join(quality["thermal_reasons"]),
            })

        return decisions, quality


def main():

    if not INPUT_FILE.exists():
        raise FileNotFoundError(INPUT_FILE)

    df = pd.read_csv(INPUT_FILE)

    required_columns = [
        "SOH_Scenario",
        "RUL_Scenario",
        "SOC_Operating_Scenario",
        "Cell",
        "Estimated_SOC_percent",
        "Estimated_Capacity_SOH_percent",
        "Estimated_Resistance_Growth_percent",
        "Capacity_Fault_Detected",
        "Resistance_Fault_Detected",
        "Capacity_RUL_cycles",
        "Resistance_RUL_cycles",
        "Estimated_Total_RUL_cycles",
        "Limiting_Mechanism",
    ]

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing diagnostic columns: {missing}"
        )

    controller = SupervisoryController()

    imu = InsulationMonitoringUnit()

    imu_reading = imu.process_measurement(
        insulation_resistance_ohm=1_000_000.0
    )

    all_decisions = []
    context_results = []

    # --------------------------------------------------------
    # Eight independent diagnostic contexts
    # --------------------------------------------------------

    grouping = [
        "SOH_Scenario",
        "RUL_Scenario",
        "SOC_Operating_Scenario",
    ]

    for context_keys, context_df in df.groupby(
        grouping,
        sort=True,
    ):

        # Synthetic runtime sensor inputs for this
        # software integration test only.
        #
        # These values are NOT extracted from the
        # unified diagnostic CSV.
        voltages = np.full(
            CELL_COUNT,
            3.35,
            dtype=float,
        )

        temperatures = np.full(
            CELL_COUNT,
            25.0,
            dtype=float,
        )

        decisions, quality = controller.evaluate_context(
            context_df=context_df,
            cell_voltages=voltages,
            cell_temperatures=temperatures,
            pack_current=10.0,
            bdu_state="CLOSED",
            protection_fault=False,
            charge_mode=True,
            insulation_state=imu_reading.insulation_state,
            insulation_measurement_quality=(
                imu_reading.measurement_quality
            ),
        )

        all_decisions.extend(decisions)

        context_results.append({

            "SOH_Scenario": context_keys[0],
            "RUL_Scenario": context_keys[1],
            "SOC_Operating_Scenario": context_keys[2],

            "Cell_Count": CELL_COUNT,

            "BDU_State": "CLOSED",
            "Thermal_State": quality["thermal_state"],

            "Thermal_Measurement_Quality":
                quality["thermal_measurement_quality"],

            "Maximum_Temperature_Spread_C":
                quality["thermal_temperature_spread_c"],

            "Charge_Derating_Recommended":
                quality["thermal_charge_derating_recommended"],

            "Discharge_Derating_Recommended":
                quality["thermal_discharge_derating_recommended"],

            "Global_Sensor_Eligibility":
                quality["global_balancing_eligible"],

            "Balancing_Eligible_Cell_Count": sum(
                item["Balancing_Eligible"]
                for item in decisions
            ),

            "Degradation_Indicator_Count": sum(
                item["Diagnostic_Severity"]
                != "NO_DEGRADATION_THRESHOLD_BREACH"
                for item in decisions
            ),
        })

    output_df = pd.DataFrame(all_decisions)

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

    checks = {

        "128 supervisory records generated":
            len(output_df) == 128,

        "All 16 cells represented":
            sorted(output_df["Cell"].unique().tolist())
            == list(range(1, CELL_COUNT + 1)),

        "Eight independent contexts preserved":
            len(context_results) == 8,

        "No missing SOC estimates":
            output_df["Estimated_SOC_percent"].notna().all(),

        "No missing SOH estimates":
            output_df[
                "Estimated_Capacity_SOH_percent"
            ].notna().all(),

        "No missing RUL estimates":
            output_df[
                "Estimated_Total_RUL_cycles"
            ].notna().all(),

        "Capacity degradation localized to Cell 8":
            output_df.loc[
                output_df["Capacity_Fault_Detected"]
                & (
                    output_df["SOH_Scenario"]
                    == "SIM-SOH-002_CAPACITY_FAULT"
                ),
                "Cell",
            ].unique().tolist() == [8],

        "Resistance degradation localized to Cell 12":
            output_df.loc[
                output_df["Resistance_Fault_Detected"]
                & (
                    output_df["SOH_Scenario"]
                    == "SIM-SOH-003_RESISTANCE_FAULT"
                ),
                "Cell",
            ].unique().tolist() == [12],

        "AI role remains advisory":
            (
                output_df["AI_Role"] == "ADVISORY_ONLY"
            ).all(),

        "BDU retains protection authority":
            (
                output_df["Protection_Authority"]
                == "BDU_ONLY"
            ).all(),

        "Balancing requires valid sensor channels":
            (
                ~output_df["Balancing_Eligible"]
                | (
                    output_df["Voltage_Sensor_Valid"]
                    & output_df["Temperature_Sensor_Valid"]
                )
            ).all(),
        "All thermal measurements valid in nominal simulation":
            output_df["Thermal_Monitoring_Valid"].all(),

        "Nominal simulation thermal state is NORMAL":
            (output_df["Thermal_State"] == "NORMAL").all(),

        "Nominal simulation does not recommend derating":
            (
                ~output_df["Charge_Derating_Recommended"]
                & ~output_df["Discharge_Derating_Recommended"]
            ).all(),

        "Balancing requires normal thermal state":
            (
                ~output_df["Balancing_Eligible"]
                | (
                    (output_df["Thermal_State"] == "NORMAL")
                    & output_df["Thermal_Monitoring_Valid"]
                )
            ).all(),

        "Thermal interlock agrees with balancing eligibility":
            (
                ~output_df["Balancing_Eligible"]
                | ~output_df["Thermal_Balancing_Interlock"]
            ).all(),

        "BDU retains protection authority":
            (output_df["Protection_Authority"] == "BDU_ONLY").all(),
    }

    # --------------------------------------------------------
    # Export
    # --------------------------------------------------------

    OUTPUT_CSV.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_df.to_csv(
        OUTPUT_CSV,
        index=False,
    )

    summary = {

        "project":
            "Simulation-First 16S Intelligent BMS",

        "module":
            "Supervisory Decision Layer",

        "record_count":
            len(output_df),

        "context_count":
            len(context_results),

        "cell_count":
            CELL_COUNT,

        "contexts":
            context_results,

        "validation": {
            name: bool(value)
            for name, value in checks.items()
        },

        "overall":
            "PASS" if all(checks.values()) else "FAIL",

        "limitations": [

            "SOC and SOH/RUL contexts remain independently generated.",

            "Runtime sensor values in this test are synthetic.",

            "Voltage and temperature are not present in the unified diagnostic CSV.",

            "RUL is an advisory estimate, not a protection threshold.",

            "Evidence grades are categorical, not calibrated probabilities.",

            "BDU protection remains independent of AI and supervisory outputs.",

            "This is software-level integration, not physical BMS validation.",
        ],
    }

    with OUTPUT_JSON.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            summary,
            file,
            indent=4,
        )

    # --------------------------------------------------------
    # Print results
    # --------------------------------------------------------

    print("=" * 70)
    print("16S SUPERVISORY DECISION LAYER")
    print("=" * 70)

    print("Diagnostic records:", len(output_df))
    print("Independent contexts:", len(context_results))

    print("\nDEGRADATION SUMMARY")

    print(
        output_df.groupby(
            ["SOH_Scenario", "Fault_Classification"]
        ).size().to_string()
    )

    print("\nVALIDATION RESULTS")

    for name, passed in checks.items():
        print(
            f"{name}: {'PASS' if passed else 'FAIL'}"
        )

    overall = all(checks.values())

    print(
        "\nOVERALL:",
        "PASS" if overall else "FAIL",
    )

    print("\nGenerated files:")
    print(OUTPUT_CSV)
    print(OUTPUT_JSON)

    if not overall:
        raise SystemExit(1)


if __name__ == "__main__":
    main()