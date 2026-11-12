"""Generate software-only BDU threshold fault-injection evidence."""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from software.protection.lfp_16s_protection_bdu import (  # noqa: E402
    ProtectionBDU,
    ProtectionInputs,
)

SAMPLE_INTERVAL_S = 0.001


def _base_inputs() -> ProtectionInputs:
    return ProtectionInputs(
        cell_voltages_v=[3.3] * 16,
        pack_current_a=10.0,
        cell_temperatures_c=[25.0] * 16,
        pack_voltage_v=52.8,
        bus_voltage_v=52.8,
    )


def _fault_cases() -> list[tuple[str, str, Callable[[ProtectionInputs], ProtectionInputs]]]:
    def cell_voltage(index: int, value: float) -> Callable[[ProtectionInputs], ProtectionInputs]:
        def inject(inputs: ProtectionInputs) -> ProtectionInputs:
            voltages = inputs.cell_voltages_v.copy()
            voltages[index] = value
            return replace(inputs, cell_voltages_v=voltages)

        return inject

    def temperature(index: int, value: float) -> Callable[[ProtectionInputs], ProtectionInputs]:
        def inject(inputs: ProtectionInputs) -> ProtectionInputs:
            temperatures = inputs.cell_temperatures_c.copy()
            temperatures[index] = value
            return replace(inputs, cell_temperatures_c=temperatures)

        return inject

    return [
        ("cell_overvoltage", "CELL_1_OVERVOLTAGE", cell_voltage(0, 3.61)),
        ("cell_undervoltage", "CELL_1_UNDERVOLTAGE", cell_voltage(0, 1.99)),
        ("cell_overtemperature", "CELL_1_OVERTEMPERATURE", temperature(0, 65.1)),
        (
            "pack_overcurrent",
            "PACK_OVERCURRENT",
            lambda inputs: replace(inputs, pack_current_a=100.1),
        ),
        (
            "invalid_cell_measurement",
            "CELL_1_VOLTAGE_INVALID",
            cell_voltage(0, float("nan")),
        ),
    ]


def run_fault_injections() -> dict[str, object]:
    cases = []
    for name, expected_fault, inject in _fault_cases():
        bdu = ProtectionBDU()
        baseline = _base_inputs()
        bdu.update(baseline, dt_s=SAMPLE_INTERVAL_S)
        result = bdu.update(
            inject(_base_inputs()),
            dt_s=SAMPLE_INTERVAL_S,
        )
        outputs = result["actuator_outputs"]
        row = {
            "scenario": name,
            "expected_fault": expected_fault,
            "detected_faults": result["active_faults"],
            "state": result["state"],
            "modeled_logic_latency_ms": SAMPLE_INTERVAL_S * 1000.0,
            "main_contactor_command": outputs["main_contactor_command"],
            "precharge_contactor_command": outputs["precharge_contactor_command"],
            "pass": (
                expected_fault in result["active_faults"]
                and result["state"] == "FAULT"
                and not outputs["main_contactor_command"]
                and not outputs["precharge_contactor_command"]
            ),
        }
        cases.append(row)

    if not all(row["pass"] for row in cases):
        failed = [row["scenario"] for row in cases if not row["pass"]]
        raise RuntimeError(f"Software fault-injection cases failed: {failed}")

    return {
        "evidence_class": "software threshold-logic fault injection",
        "status": "research-only; ProtectionConfig defaults are not approved limits",
        "sample_interval_ms": SAMPLE_INTERVAL_S * 1000.0,
        "modeled_logic_latency_boundary": (
            "Latency is one software update interval after a fault value is supplied. "
            "Sensor conversion/filtering, scheduling jitter, hardware inhibit propagation, "
            "coil current decay, and contactor opening are not modeled."
        ),
        "not_demonstrated": [
            "NTC resistance-to-temperature curve or thermal response",
            "AFE open-wire detection; invalid input is only a software quality fault",
            "fuse, contactor, or short-circuit trip curve",
            "physical fault-to-isolation response time",
        ],
        "limitations": [
            "ProtectionConfig defaults are software-test thresholds, not approved hardware limits.",
            "The 1-ms result is one model update interval after a value is supplied.",
            "Sensor conversion, filtering, scheduler jitter, hardware inhibit, and actuator dynamics are excluded.",
        ],
        "scenarios": cases,
    }


def main() -> None:
    report = run_fault_injections()
    metrics_dir = ROOT / "results" / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)

    json_path = metrics_dir / "software_fault_injection_report.json"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    csv_path = metrics_dir / "software_fault_injection_report.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(report["scenarios"][0]))
        writer.writeheader()
        for scenario in report["scenarios"]:
            writer.writerow(
                {
                    **scenario,
                    "detected_faults": ";".join(scenario["detected_faults"]),
                }
            )

    print(f"Report: {json_path.relative_to(ROOT)}")
    print(f"CSV: {csv_path.relative_to(ROOT)}")
    print(f"Passing scenarios: {len(report['scenarios'])}/{len(report['scenarios'])}")


if __name__ == "__main__":
    main()
