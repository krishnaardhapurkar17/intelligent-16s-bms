"""Reproduce synthetic dynamic-load SOC initialization experiments."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from software.estimation.soc_drive_cycle import (  # noqa: E402
    run_soc_initialization_scenario,
)


def main() -> None:
    scenarios = [
        {
            "name": "high_soc_observable_ocv",
            "true_initial_soc": 0.95,
            "estimated_initial_soc": 0.80,
        },
        {
            "name": "mid_soc_flat_ocv",
            "true_initial_soc": 0.55,
            "estimated_initial_soc": 0.70,
        },
    ]
    records = []
    scenario_metrics = []
    for scenario in scenarios:
        rows, metrics = run_soc_initialization_scenario(**scenario)
        records.extend(rows)
        scenario_metrics.append(metrics)

    high_soc, flat_soc = scenario_metrics
    if not high_soc["rest_ocv_correction_applied"]:
        raise RuntimeError("The high-SOC OCV-correction scenario did not apply correction")
    if abs(high_soc["final_ocv_fused_error_percentage_points"]) >= abs(
        high_soc["final_coulomb_count_error_percentage_points"]
    ):
        raise RuntimeError("The high-SOC OCV correction did not reduce the initial error")
    if flat_soc["rest_ocv_correction_applied"]:
        raise RuntimeError("The flat-plateau OCV correction should be rejected")

    metrics_dir = ROOT / "results" / "metrics"
    figure_dir = ROOT / "docs" / "figures"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)

    csv_path = metrics_dir / "soc_drive_cycle_initialization.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)

    report = {
        "evidence_class": "synthetic software-model experiment",
        "status": "research-only; no standardized drive cycle or independent SOC ground truth",
        "model_source": "models/battery-parameters/lf100la_ecm_assumptions.json",
        "model_boundary": (
            "Provisional first-order Thevenin ECM; synthetic current/regen profile; "
            "ideal current sensing and rest OCV; no temperature or cell-to-cell variation."
        ),
        "limitations": [
            "The current profile is synthetic and is not WLTP/UDDS data.",
            "ECM parameters and OCV curve are not manufacturer-validated.",
            "Current sensing and rest OCV are ideal; the experiment is not independent cell validation.",
            "No temperature dependence, cell variation, sensor error, or physical hardware is modeled.",
        ],
        "profile": {
            "name": "deterministic 120-second pulse/regen profile",
            "standardized_wltp_or_udds": False,
            "duration_s": 1800,
            "rest_duration_s": 300,
            "time_step_s": 1,
        },
        "ocv_fusion": {
            "weight": 0.70,
            "minimum_slope_v_per_soc_percentage_point": 0.0025,
            "correction_timing": "once, after the 300-second rest",
        },
        "scenarios": scenario_metrics,
    }
    report_path = metrics_dir / "soc_drive_cycle_initialization.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    figure, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    for axis, scenario in zip(axes, scenarios):
        subset = [row for row in records if row["scenario"] == scenario["name"]]
        time_minutes = [row["time_s"] / 60.0 for row in subset]
        axis.plot(
            time_minutes,
            [row["true_soc_percent"] for row in subset],
            label="True SOC (synthetic model)",
            linewidth=2,
        )
        axis.plot(
            time_minutes,
            [row["coulomb_count_soc_percent"] for row in subset],
            label="Coulomb-count estimate",
            linestyle="--",
        )
        axis.plot(
            time_minutes,
            [row["ocv_fused_soc_percent"] for row in subset],
            label="CC + rest OCV correction",
            linestyle="-.",
        )
        axis.axvline(30, color="grey", linestyle=":", label="Drive ends / rest begins")
        axis.set_ylabel("SOC (%)")
        axis.set_title(scenario["name"].replace("_", " "))
        axis.grid(True, alpha=0.3)
        axis.legend(loc="best")
    axes[-1].set_xlabel("Time (minutes)")
    figure.suptitle("SOC initialization-error experiment (synthetic, not WLTP/UDDS)")
    figure.tight_layout()
    figure_path = figure_dir / "soc_drive_cycle_initialization.png"
    figure.savefig(figure_path, dpi=160)
    plt.close(figure)

    print(f"Report: {report_path.relative_to(ROOT)}")
    print(f"Waveforms: {figure_path.relative_to(ROOT)}")
    for metrics in scenario_metrics:
        print(
            f"{metrics['scenario']}: initial error "
            f"{metrics['initial_soc_error_percentage_points']:.1f} pp; "
            f"final fused error {metrics['final_ocv_fused_error_percentage_points']:.2f} pp; "
            f"correction={metrics['rest_ocv_correction_reason']}"
        )


if __name__ == "__main__":
    main()
