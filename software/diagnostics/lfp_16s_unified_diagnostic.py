
import json
import numpy as np
import pandas as pd
from pathlib import Path

# ============================================================
# 16S LFP UNIFIED BMS DIAGNOSTIC LAYER
# Integrates SOC + SOH + RUL
#
# Simulation-only integration.
# SOC operating scenarios and SOH/RUL aging scenarios
# are kept separately identified.
# ============================================================

CELL_COUNT = 16

BASE_DIR = Path(__file__).resolve().parents[2]

METRICS_DIR = BASE_DIR / "results" / "metrics"
METRICS_DIR.mkdir(parents=True, exist_ok=True)

SOC_FILE = METRICS_DIR / "lfp_16s_ocv_soc_fusion.csv"
SOH_FILE = METRICS_DIR / "lfp_16s_soh_estimation.csv"
RUL_FILE = METRICS_DIR / "lfp_16s_rul_estimation.csv"

OUTPUT_CSV = (
    METRICS_DIR / "lfp_16s_unified_diagnostics.csv"
)

OUTPUT_JSON = (
    METRICS_DIR / "lfp_16s_unified_summary.json"
)

# ------------------------------------------------------------
# Diagnostic thresholds
# These are provisional simulation thresholds.
# ------------------------------------------------------------

CAPACITY_SOH_THRESHOLD = 90.0
RESISTANCE_GROWTH_THRESHOLD = 20.0

# Explicit mapping between independently named SOH and RUL
# scenarios. These pairs share the same injected fault setup.
SCENARIO_MAPPING = {
    "SIM-SOH-001_HEALTHY": "SIM-RUL-001_HEALTHY",

    "SIM-SOH-002_CAPACITY_FAULT":
        "SIM-RUL-002_CAPACITY_AGING",

    "SIM-SOH-003_RESISTANCE_FAULT":
        "SIM-RUL-003_RESISTANCE_AGING",

    "SIM-SOH-004_COMBINED_FAULT":
        "SIM-RUL-004_COMBINED_AGING"
}


# ============================================================
# LOAD INPUT DATA
# ============================================================

def load_input_files():

    for file_path in [SOC_FILE, SOH_FILE, RUL_FILE]:

        if not file_path.exists():
            raise FileNotFoundError(
                f"Required input file not found: {file_path}"
            )

    soc_df = pd.read_csv(SOC_FILE)
    soh_df = pd.read_csv(SOH_FILE)
    rul_df = pd.read_csv(RUL_FILE)

    print("=" * 70)
    print("UNIFIED BMS DIAGNOSTIC DATA INTEGRATION")
    print("=" * 70)

    print("\nINPUT DATA")
    print(f"SOC records: {len(soc_df)}")
    print(f"SOH records: {len(soh_df)}")
    print(f"RUL records: {len(rul_df)}")

    return soc_df, soh_df, rul_df


# ============================================================
# EXTRACT LATEST SOC SNAPSHOT FOR EACH OPERATING SCENARIO
# ============================================================

def extract_soc_snapshots(soc_df):

    snapshots = []

    required_scenarios = [
        "OCV_CORRECTION_REGION",
        "LFP_FLAT_REGION"
    ]

    for scenario in required_scenarios:

        scenario_df = soc_df[
            soc_df["Scenario"] == scenario
        ].copy()

        if scenario_df.empty:
            raise ValueError(
                f"SOC scenario missing: {scenario}"
            )

        scenario_df = scenario_df.sort_values(
            "Time_seconds"
        )

        latest = scenario_df.iloc[-1]

        for cell in range(1, CELL_COUNT + 1):

            fused_column = f"Fused_SOC_Cell_{cell}"
            cc_column = (
                f"Coulomb_Counting_SOC_Cell_{cell}"
            )
            true_column = f"True_SOC_Cell_{cell}"

            required_columns = [
                fused_column,
                cc_column,
                true_column
            ]

            for column in required_columns:

                if column not in soc_df.columns:
                    raise ValueError(
                        f"Missing SOC column: {column}"
                    )

            snapshots.append({

                "SOC_Operating_Scenario": scenario,

                "SOC_Snapshot_Time_seconds":
                    float(latest["Time_seconds"]),

                "Cell": cell,

                "True_SOC_percent":
                    float(latest[true_column]),

                "Coulomb_Counting_SOC_percent":
                    float(latest[cc_column]),

                "Estimated_SOC_percent":
                    float(latest[fused_column])
            })

    return pd.DataFrame(snapshots)


# ============================================================
# PREPARE SOH AND RUL DATA
# ============================================================

def prepare_soh_rul(soh_df, rul_df):

    required_soh = [
        "Scenario",
        "Cell",
        "Estimated_Capacity_SOH_percent",
        "Estimated_Resistance_Growth_percent",
        "Capacity_Fault_Detected",
        "Resistance_Fault_Detected"
    ]

    required_rul = [
        "Scenario",
        "Cell",
        "Estimated_Capacity_RUL_cycles",
        "Estimated_Resistance_RUL_cycles",
        "Estimated_Total_RUL_cycles",
        "Limiting_Mechanism"
    ]

    for column in required_soh:

        if column not in soh_df.columns:
            raise ValueError(
                f"Missing SOH column: {column}"
            )

    for column in required_rul:

        if column not in rul_df.columns:
            raise ValueError(
                f"Missing RUL column: {column}"
            )

    # Rename RUL scenario field to preserve both identifiers.
    rul_df = rul_df.rename(
        columns={"Scenario": "RUL_Scenario"}
    )

    soh_df = soh_df.rename(
        columns={"Scenario": "SOH_Scenario"}
    )

    # Apply explicit scenario mapping.
    soh_df["RUL_Scenario"] = (
        soh_df["SOH_Scenario"].map(SCENARIO_MAPPING)
    )

    if soh_df["RUL_Scenario"].isna().any():
        raise ValueError(
            "An SOH scenario has no RUL scenario mapping."
        )

    merged = pd.merge(
        soh_df,
        rul_df,
        on=["RUL_Scenario", "Cell"],
        how="inner",
        validate="one_to_one"
    )

    expected_records = (
        len(SCENARIO_MAPPING) * CELL_COUNT
    )

    if len(merged) != expected_records:
        raise ValueError(
            f"Expected {expected_records} SOH/RUL records, "
            f"received {len(merged)}."
        )

    return merged


# ============================================================
# BUILD UNIFIED DATASET
# ============================================================

def build_unified_dataset(
    soc_snapshots,
    soh_rul_df
):

    unified_rows = []

    for _, aging_row in soh_rul_df.iterrows():

        soh_scenario = aging_row["SOH_Scenario"]

        for _, soc_row in soc_snapshots.iterrows():

            if int(aging_row["Cell"]) != int(soc_row["Cell"]):
                continue

            raw_capacity_soh = float(
                aging_row["Estimated_Capacity_SOH_percent"]
            )

            # Preserve the raw estimator output for auditability.
            # Constrain the reported SOH indicator to 0-100%.
            capacity_soh = float(
                np.clip(raw_capacity_soh, 0.0, 100.0)
            )

            resistance_growth = float(
                aging_row["Estimated_Resistance_Growth_percent"]
            )

            capacity_rul = float(
                aging_row["Estimated_Capacity_RUL_cycles"]
            )

            resistance_rul = float(
                aging_row["Estimated_Resistance_RUL_cycles"]
            )

            total_rul = float(
                aging_row["Estimated_Total_RUL_cycles"]
            )

            capacity_fault = (
                capacity_soh < CAPACITY_SOH_THRESHOLD
            )

            resistance_fault = (
                resistance_growth
                > RESISTANCE_GROWTH_THRESHOLD
            )

            if capacity_fault and resistance_fault:
                health_status = "MULTIPLE_DEGRADATION_INDICATORS"

            elif capacity_fault:
                health_status = "CAPACITY_DEGRADATION"

            elif resistance_fault:
                health_status = "RESISTANCE_DEGRADATION"

            else:
                health_status = "NO_THRESHOLD_BREACH"

            limiting_mechanism = str(
                aging_row["Limiting_Mechanism"]
            )

            unified_rows.append({

                "SOH_Scenario": soh_scenario,

                "RUL_Scenario":
                    aging_row["RUL_Scenario"],

                "SOC_Operating_Scenario":
                    soc_row["SOC_Operating_Scenario"],

                "Cell": int(aging_row["Cell"]),

                "SOC_Snapshot_Time_seconds":
                    soc_row["SOC_Snapshot_Time_seconds"],

                "Estimated_SOC_percent":
                    soc_row["Estimated_SOC_percent"],

                "True_SOC_percent":
                    soc_row["True_SOC_percent"],

                "Raw_Estimated_Capacity_SOH_percent":
                    raw_capacity_soh,

                "Estimated_Capacity_SOH_percent":
                    capacity_soh,

                "Estimated_Resistance_Growth_percent":
                    resistance_growth,

                "Capacity_Fault_Detected":
                    bool(capacity_fault),

                "Resistance_Fault_Detected":
                    bool(resistance_fault),

                "Capacity_RUL_cycles":
                    capacity_rul,

                "Resistance_RUL_cycles":
                    resistance_rul,

                "Estimated_Total_RUL_cycles":
                    total_rul,

                "Limiting_Mechanism":
                    limiting_mechanism,

                "Health_Status":
                    health_status
            })

    return pd.DataFrame(unified_rows)


# ============================================================
# VALIDATION
# ============================================================

def validate_dataset(unified_df):

    checks = {}

    expected_rows = (
        len(SCENARIO_MAPPING)
        * 2
        * CELL_COUNT
    )

    checks["Expected 128 integrated records"] = (
        len(unified_df) == expected_rows
    )

    checks["All 16 cells represented"] = (
        sorted(unified_df["Cell"].unique().tolist())
        == list(range(1, CELL_COUNT + 1))
    )

    checks["Four SOH scenarios represented"] = (
        unified_df["SOH_Scenario"].nunique() == 4
    )

    checks["Two SOC operating scenarios represented"] = (
        unified_df["SOC_Operating_Scenario"].nunique() == 2
    )

    checks["No missing SOC estimates"] = (
        unified_df["Estimated_SOC_percent"].notna().all()
    )

    checks["No missing capacity SOH estimates"] = (
        unified_df[
            "Estimated_Capacity_SOH_percent"
        ].notna().all()
    )

    checks["No missing resistance estimates"] = (
        unified_df[
            "Estimated_Resistance_Growth_percent"
        ].notna().all()
    )

    checks["No missing RUL estimates"] = (
        unified_df[
            "Estimated_Total_RUL_cycles"
        ].notna().all()
    )

    checks["SOC values within physical limits"] = (
        unified_df["Estimated_SOC_percent"]
        .between(0, 100).all()
    )

    checks["Capacity SOH values within physical limits"] = (
        unified_df[
            "Estimated_Capacity_SOH_percent"
        ].between(0, 100).all()
    )

    checks["RUL values non-negative"] = (
        (unified_df["Estimated_Total_RUL_cycles"] >= 0).all()
    )

    # Verify injected faults remain localized.
    capacity_fault_rows = unified_df[
        unified_df["SOH_Scenario"]
        == "SIM-SOH-002_CAPACITY_FAULT"
    ]

    resistance_fault_rows = unified_df[
        unified_df["SOH_Scenario"]
        == "SIM-SOH-003_RESISTANCE_FAULT"
    ]

    combined_rows = unified_df[
        unified_df["SOH_Scenario"]
        == "SIM-SOH-004_COMBINED_FAULT"
    ]

    for soc_scenario in unified_df[
        "SOC_Operating_Scenario"
    ].unique():

        cap_group = capacity_fault_rows[
            capacity_fault_rows["SOC_Operating_Scenario"]
            == soc_scenario
        ]

        res_group = resistance_fault_rows[
            resistance_fault_rows["SOC_Operating_Scenario"]
            == soc_scenario
        ]

        combined_group = combined_rows[
            combined_rows["SOC_Operating_Scenario"]
            == soc_scenario
        ]

        checks[
            f"Capacity fault localized to Cell 8 ({soc_scenario})"
        ] = (
            cap_group.loc[
                cap_group["Capacity_Fault_Detected"],
                "Cell"
            ].tolist() == [8]
        )

        checks[
            f"Resistance fault localized to Cell 12 ({soc_scenario})"
        ] = (
            res_group.loc[
                res_group["Resistance_Fault_Detected"],
                "Cell"
            ].tolist() == [12]
        )

        checks[
            f"Combined degradation detected ({soc_scenario})"
        ] = (
            combined_group.loc[
                combined_group["Capacity_Fault_Detected"],
                "Cell"
            ].tolist() == [8]
            and
            combined_group.loc[
                combined_group["Resistance_Fault_Detected"],
                "Cell"
            ].tolist() == [12]
        )

    return checks


# ============================================================
# GENERATE SUMMARY
# ============================================================

def generate_summary(unified_df, checks):

    scenario_summaries = []

    grouping = [
        "SOH_Scenario",
        "SOC_Operating_Scenario"
    ]

    for keys, group in unified_df.groupby(grouping):

        soh_scenario, soc_scenario = keys

        limiting_cell_row = group.loc[
            group["Estimated_Total_RUL_cycles"].idxmin()
        ]

        scenario_summaries.append({

            "SOH_Scenario": soh_scenario,

            "SOC_Operating_Scenario": soc_scenario,

            "Cell_Count": int(group["Cell"].nunique()),

            "Capacity_Fault_Count": int(
                group["Capacity_Fault_Detected"].sum()
            ),

            "Resistance_Fault_Count": int(
                group["Resistance_Fault_Detected"].sum()
            ),

            "Limiting_Cell": int(
                limiting_cell_row["Cell"]
            ),

            "Limiting_Mechanism":
                limiting_cell_row["Limiting_Mechanism"],

            "Minimum_RUL_cycles": float(
                limiting_cell_row[
                    "Estimated_Total_RUL_cycles"
                ]
            )
        })

    return {
        "project": "Simulation-First 16S Intelligent BMS",

        "integration_type":
            "SOC operating scenarios cross-joined with aging scenarios",

        "record_count": int(len(unified_df)),

        "cell_count": CELL_COUNT,

        "soc_operating_scenarios": sorted(
            unified_df[
                "SOC_Operating_Scenario"
            ].unique().tolist()
        ),

        "aging_scenarios": sorted(
            unified_df["SOH_Scenario"].unique().tolist()
        ),

        "scenario_summaries": scenario_summaries,

        "validation": {
            name: bool(passed)
            for name, passed in checks.items()
        },

        "all_checks_passed": bool(
            all(checks.values())
        ),

        "limitations": [
            "SOC and SOH/RUL are independently generated scenarios.",
            "The combined dataset is a scenario cross-product, not a synchronized physical test.",
            "RUL is based on synthetic linear degradation extrapolation.",
            "No cell voltage or temperature fields are included in this integration.",
            "Health thresholds are provisional simulation parameters."
        ]
    }


# ============================================================
# MAIN
# ============================================================

def main():

    soc_df, soh_df, rul_df = load_input_files()

    print("\nExtracting SOC snapshots...")

    soc_snapshots = extract_soc_snapshots(
        soc_df
    )

    print(
        f"SOC snapshots extracted: {len(soc_snapshots)}"
    )

    print("\nPreparing SOH and RUL records...")

    soh_rul_df = prepare_soh_rul(
        soh_df,
        rul_df
    )

    print(
        f"Matched SOH/RUL records: {len(soh_rul_df)}"
    )

    print("\nBuilding unified diagnostic dataset...")

    unified_df = build_unified_dataset(
        soc_snapshots,
        soh_rul_df
    )

    unified_df = unified_df.sort_values(
        [
            "SOH_Scenario",
            "SOC_Operating_Scenario",
            "Cell"
        ]
    ).reset_index(drop=True)

    unified_df.to_csv(
        OUTPUT_CSV,
        index=False
    )

    checks = validate_dataset(
        unified_df
    )

    summary = generate_summary(
        unified_df,
        checks
    )

    with open(
        OUTPUT_JSON,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            summary,
            file,
            indent=4
        )

    print("\n" + "=" * 70)
    print("UNIFIED BMS DIAGNOSTIC RESULTS")
    print("=" * 70)

    print("\nTOTAL RECORDS:", len(unified_df))

    print("\nSCENARIO SUMMARY")

    summary_df = pd.DataFrame(
        summary["scenario_summaries"]
    )

    print(
        summary_df.to_string(index=False)
    )

    print("\nVALIDATION RESULTS")

    for name, passed in checks.items():

        print(
            f"{name}: "
            f"{'PASS' if passed else 'FAIL'}"
        )

    print(
        "\nOVERALL:",
        "PASS" if all(checks.values()) else "FAIL"
    )

    print("\nGENERATED FILES")
    print(OUTPUT_CSV)
    print(OUTPUT_JSON)

    overall = all(checks.values())

    print(
        "\nOVERALL:",
        "PASS" if overall else "FAIL"
    )

    print("\nGENERATED FILES")
    print(OUTPUT_CSV)
    print(OUTPUT_JSON)

    if not overall:
        raise SystemExit(1)

    print("\nUNIFIED BMS DIAGNOSTIC INTEGRATION COMPLETE")


if __name__ == "__main__":
    main()
