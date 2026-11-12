"""Reproduce the assumption-only external precharge R-C simulation."""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import asdict
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from models.electrical.precharge_rc import (  # noqa: E402
    PrechargeParameters,
    simulate_precharge,
)


def main() -> None:
    parameters = PrechargeParameters()
    normal_samples, normal_metrics = simulate_precharge(parameters)
    fault_samples, fault_metrics = simulate_precharge(
        parameters,
        charging_path_available=False,
    )

    if normal_metrics["state"] != "CLOSED":
        raise RuntimeError("Precharge assumptions failed to reach the close threshold")
    if fault_metrics["state"] != "FAULT":
        raise RuntimeError("Blocked-path scenario did not fail safe")
    if fault_metrics["main_contactor_command"]:
        raise RuntimeError("Blocked-path scenario commanded the main contactor")

    metrics_dir = ROOT / "results" / "metrics"
    figure_dir = ROOT / "docs" / "figures"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)

    csv_path = metrics_dir / "precharge_assumption_simulation.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=["scenario", *asdict(normal_samples[0])])
        writer.writeheader()
        for scenario, samples in (
            ("nominal_rc", normal_samples),
            ("blocked_precharge_path", fault_samples),
        ):
            for sample in samples:
                writer.writerow({"scenario": scenario, **asdict(sample)})

    report = {
        "evidence_class": "analytical R-C model verification",
        "status": "research-only; not an approved design limit",
        "model_boundary": (
            "Ideal voltage source, series resistor, and DC-link capacitor. "
            "No source impedance, load, leakage, tolerance, switching transient, "
            "contactor dynamics, component model, KiCad simulation, or hardware test."
        ),
        "limitations": [
            "The resistor, capacitor, source, and threshold are illustrative project assumptions.",
            "The ideal R-C model excludes source impedance, load, leakage, tolerance, and thermal coupling.",
            "No vendor component model, KiCad SPICE run, contactor dynamics, or physical test is included.",
        ],
        "assumption_source": "hardware/circuit-definition.md precharge example",
        "parameters": asdict(parameters),
        "nominal_rc": normal_metrics,
        "blocked_precharge_path": fault_metrics,
        "checks": {
            "nominal_reaches_close_delta_before_timeout": (
                normal_metrics["state"] == "CLOSED"
                and normal_metrics["simulated_close_time_s"] is not None
                and normal_metrics["simulated_close_time_s"] <= parameters.timeout_s
            ),
            "blocked_path_times_out_without_main_close": (
                fault_metrics["state"] == "FAULT"
                and not fault_metrics["main_contactor_command"]
            ),
        },
    }
    report_path = metrics_dir / "precharge_assumption_simulation.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    figure_path = figure_dir / "precharge_assumption_waveforms.png"
    figure, voltage_axis = plt.subplots(figsize=(9, 5))
    for label, samples in (
        ("Nominal R-C", normal_samples),
        ("Blocked path", fault_samples),
    ):
        times = [sample.time_s for sample in samples]
        voltage_axis.plot(
            times,
            [sample.bus_voltage_v for sample in samples],
            label=f"{label}: bus voltage",
        )
    voltage_axis.axhline(
        parameters.pack_voltage_v - parameters.close_delta_v,
        color="black",
        linestyle="--",
        label="Main-close threshold",
    )
    voltage_axis.set(
        xlabel="Time (s)",
        ylabel="Bus voltage (V)",
        title="Illustrative precharge R-C model (not KiCad or hardware validation)",
    )
    voltage_axis.grid(True, alpha=0.3)
    voltage_axis.legend()
    figure.tight_layout()
    figure.savefig(figure_path, dpi=160)
    plt.close(figure)

    print(f"Report: {report_path.relative_to(ROOT)}")
    print(f"Waveforms: {figure_path.relative_to(ROOT)}")
    print(f"Nominal close time: {normal_metrics['simulated_close_time_s']:.3f} s")
    print(f"Blocked path result: {fault_metrics['state']}")


if __name__ == "__main__":
    main()
