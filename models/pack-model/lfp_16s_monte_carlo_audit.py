
from pathlib import Path
import json

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

INPUT = ROOT / "results" / "metrics" / "lfp_16s_monte_carlo_runs.csv"

OUTPUT_CSV = ROOT / "results" / "metrics" / "lfp_16s_monte_carlo_audit.csv"
OUTPUT_JSON = ROOT / "results" / "metrics" / "lfp_16s_monte_carlo_audit.json"

df = pd.read_csv(INPUT)

required = [
    "Scenario",
    "Run",
    "Cell",
    "Resistance_Flag",
    "Voltage_Flag",
    "Temperature_Flag",
    "Voltage_Missing",
    "Temperature_Missing",
    "Temperature_Invalid",
]

missing_columns = [
    col for col in required if col not in df.columns
]

if missing_columns:
    raise ValueError(
        f"Missing CSV columns: {missing_columns}"
    )

boolean_columns = [
    "Resistance_Flag",
    "Voltage_Flag",
    "Temperature_Flag",
    "Voltage_Missing",
    "Temperature_Missing",
    "Temperature_Invalid",
]

for col in boolean_columns:
    df[col] = df[col].astype(str).str.lower().map({
        "true": True,
        "false": False,
        "1": True,
        "0": False,
    })

    if df[col].isna().any():
        raise ValueError(
            f"Invalid boolean values in {col}"
        )


def channel_rate(data, column):
    return float(data[column].mean() * 100)


def run_rate(data, column):
    per_run = data.groupby("Run")[column].any()
    return float(per_run.mean() * 100)


# ============================================================
# 1. HEALTHY SCENARIO FALSE-POSITIVE AUDIT
# ============================================================

healthy = df[
    df["Scenario"] == "SIM-018A Healthy noisy pack"
].copy()

if healthy.empty:
    raise ValueError("Healthy scenario not found.")

healthy_resistance_fp = channel_rate(
    healthy, "Resistance_Flag"
)

healthy_voltage_fp = channel_rate(
    healthy, "Voltage_Flag"
)

healthy_temperature_fp = channel_rate(
    healthy, "Temperature_Flag"
)

healthy_any_alarm = (
    healthy["Resistance_Flag"]
    | healthy["Voltage_Flag"]
    | healthy["Temperature_Flag"]
)

healthy_overall_fp = float(
    healthy_any_alarm.mean() * 100
)

healthy_run_alarm_rate = run_rate(
    healthy.assign(Any_Alarm=healthy_any_alarm),
    "Any_Alarm"
)


# ============================================================
# 2. SOC IMBALANCE AUDIT
# ============================================================

soc = df[
    df["Scenario"] == "SIM-018B SOC imbalance"
].copy()

soc_cell8 = soc[
    soc["Cell"] == 8
]

soc_cell8_voltage_alarm = channel_rate(
    soc_cell8, "Voltage_Flag"
)

soc_resistance_fp = channel_rate(
    soc, "Resistance_Flag"
)

soc_temperature_fp = channel_rate(
    soc, "Temperature_Flag"
)


# ============================================================
# 3. TEMPERATURE VARIATION AUDIT
# ============================================================

temperature = df[
    df["Scenario"] == "SIM-018C Temperature variation"
].copy()

temperature_channel_alarm = channel_rate(
    temperature, "Temperature_Flag"
)


# ============================================================
# 4. INJECTED FAULT DETECTION RATES
# ============================================================

def injected_detection_rate(
    scenario_name,
    cell_number,
    column
):

    selected = df[
        (df["Scenario"] == scenario_name)
        & (df["Cell"] == cell_number)
    ]

    if selected.empty:
        return None

    return channel_rate(
        selected,
        column
    )


injected_results = {
    "SIM-018D_Cell8_resistance_detection_percent":
        injected_detection_rate(
            "SIM-018D Resistance fault",
            8,
            "Resistance_Flag"
        ),

    "SIM-018E_Cell8_resistance_detection_percent":
        injected_detection_rate(
            "SIM-018E Multiple faults",
            8,
            "Resistance_Flag"
        ),

    "SIM-018E_Cell12_voltage_detection_percent":
        injected_detection_rate(
            "SIM-018E Multiple faults",
            12,
            "Voltage_Flag"
        ),

    "SIM-018E_Cell14_temperature_detection_percent":
        injected_detection_rate(
            "SIM-018E Multiple faults",
            14,
            "Temperature_Flag"
        ),
}


# ============================================================
# 5. SENSOR DATA QUALITY DETECTION
# ============================================================

sensor_faults = df[
    df["Scenario"] == "SIM-018F Sensor data faults"
].copy()

sensor_results = {

    "Cell14_missing_voltage_detection_percent":
        channel_rate(
            sensor_faults[
                sensor_faults["Cell"] == 14
            ],
            "Voltage_Missing"
        ),

    "Cell15_invalid_temperature_detection_percent":
        channel_rate(
            sensor_faults[
                sensor_faults["Cell"] == 15
            ],
            "Temperature_Invalid"
        ),

    "Cell16_missing_temperature_detection_percent":
        channel_rate(
            sensor_faults[
                sensor_faults["Cell"] == 16
            ],
            "Temperature_Missing"
        ),
}


# ============================================================
# 6. BUILD AUDIT REPORT
# ============================================================

audit = {

    "experiment": "Monte Carlo diagnostic metric audit",

    "healthy_scenario": {
        "resistance_false_positive_rate_percent":
            healthy_resistance_fp,

        "voltage_alarm_rate_percent":
            healthy_voltage_fp,

        "temperature_false_positive_rate_percent":
            healthy_temperature_fp,

        "overall_channel_false_positive_rate_percent":
            healthy_overall_fp,

        "runs_with_any_alarm_percent":
            healthy_run_alarm_rate,
    },

    "soc_imbalance_scenario": {
        "cell8_voltage_alarm_rate_percent":
            soc_cell8_voltage_alarm,

        "resistance_false_positive_rate_percent":
            soc_resistance_fp,

        "temperature_false_positive_rate_percent":
            soc_temperature_fp,

        "interpretation": (
            "A voltage deviation under SOC imbalance is an "
            "unresolved operating-condition anomaly, not "
            "proof of a faulty cell or sensor."
        ),
    },

    "temperature_variation_scenario": {
        "temperature_alarm_rate_percent":
            temperature_channel_alarm
    },

    "injected_fault_detection": injected_results,

    "sensor_data_fault_detection": sensor_results,

    "limitations": [
        "This audit reuses existing Monte Carlo runs.",
        "Voltage alarms are not equivalent to confirmed voltage sensor faults.",
        "The overall false-positive rate is a channel-level rate.",
        "The results apply only to the existing simulated assumptions."
    ],
}


# ============================================================
# 7. SAVE REPORT
# ============================================================

rows = []

for section, values in audit.items():

    if isinstance(values, dict):

        for metric, value in values.items():

            if isinstance(value, (int, float)) or value is None:

                rows.append({
                    "Section": section,
                    "Metric": metric,
                    "Value": value,
                })

audit_df = pd.DataFrame(rows)

audit_df.to_csv(
    OUTPUT_CSV,
    index=False
)

with open(
    OUTPUT_JSON,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        audit,
        f,
        indent=4
    )


# ============================================================
# 8. PRINT REPORT
# ============================================================

print("=" * 75)
print("MONTE CARLO METRIC AUDIT")
print("=" * 75)

print("\nHEALTHY PACK FALSE-POSITIVE AUDIT")

for key, value in audit["healthy_scenario"].items():

    print(f"{key}: {value:.3f}%")

print("\nSOC IMBALANCE AUDIT")

for key, value in audit["soc_imbalance_scenario"].items():

    if isinstance(value, (int, float)):
        print(f"{key}: {value:.3f}%")

print("\nTEMPERATURE VARIATION AUDIT")

print(
    "Temperature alarm rate:",
    f"{temperature_channel_alarm:.3f}%"
)

print("\nINJECTED FAULT DETECTION")

for key, value in injected_results.items():

    print(f"{key}: {value}%")

print("\nSENSOR DATA QUALITY")

for key, value in sensor_results.items():

    print(f"{key}: {value:.3f}%")

print("\nGENERATED FILES")
print(OUTPUT_CSV)
print(OUTPUT_JSON)

print("\nMONTE CARLO AUDIT COMPLETE")
