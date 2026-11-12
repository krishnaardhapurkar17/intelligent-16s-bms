"""Compare generic adjacent-cell transfer with resistor bleed under matched conditions."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ACTIVE_PATH = ROOT / "models" / "balancing" / "lfp_16s_switched_cap_active_balancing.py"
PASSIVE_PATH = ROOT / "models" / "balancing" / "lfp_16s_passive_balancing.py"
OUT_METRICS = ROOT / "results" / "metrics"
OUT_FIGURES = ROOT / "results" / "figures"
INITIAL_SOC = np.array([0.92, 0.84, 0.82, 0.80, 0.79, 0.78, 0.77, 0.76,
                        0.75, 0.74, 0.73, 0.72, 0.71, 0.70, 0.69, 0.68])
DT_S = 60.0
MAX_HOURS = 1000.0


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_passive() -> dict:
    passive = load_module("passive_baseline", PASSIVE_PATH)
    # Match the active model's voltage-equivalent SOC thresholds.
    passive.BALANCE_START_DELTA_V = 0.6 * 0.01
    passive.BALANCE_STOP_DELTA_V = 0.6 * 0.005
    passive.TIME_STEP_S = DT_S
    passive.SIMULATION_DURATION_S = MAX_HOURS * 3600
    cells = passive.CellBank(INITIAL_SOC * 100.0)
    controller = passive.PassiveBalancer()
    energy_wh = elapsed_s = 0.0
    for _ in range(int(MAX_HOURS * 3600 / DT_S)):
        if np.ptp(cells.soc) <= 0.5:
            break
        enabled = controller.update_eligibility(cells.voltage, cells.temperature,
                                                "CLOSED", True, False)
        cells.update(enabled, DT_S)
        energy_wh = float(np.sum(cells.dissipated_energy_wh))
        elapsed_s += DT_S
    final = cells.soc / 100.0
    return {"final_soc": final, "elapsed_s": elapsed_s,
            "range_initial": float(np.ptp(INITIAL_SOC)),
            "range_final": float(np.ptp(final)),
            "delivered_energy_wh": 0.0,
            "loss_energy_wh": energy_wh,
            "charge_conservation_error_ah": float((np.sum(final)-np.sum(INITIAL_SOC))*100.0),
            "max_temperature_c": float(np.max(cells.temperature)),
            "converged": bool(np.ptp(cells.soc) <= 0.5)}


def main() -> int:
    active = load_module("active_model", ACTIVE_PATH)
    active_result = active.run_active(INITIAL_SOC, dt_s=DT_S, max_hours=MAX_HOURS)
    passive_result = run_passive()
    rows = []
    for strategy, result in (("shared_capacitor_bank_abstraction", active_result),
                             ("resistor_bleed_passive_baseline", passive_result)):
        rows.append({"strategy": strategy,
                     "initial_soc_range_pct": 100 * result["range_initial"],
                     "final_soc_range_pct": 100 * result["range_final"],
                     "elapsed_hours": result["elapsed_s"] / 3600,
                     "delivered_energy_wh": result["delivered_energy_wh"],
                     "modeled_loss_energy_wh": result["loss_energy_wh"],
                     "net_charge_change_ah": result["charge_conservation_error_ah"],
                     "maximum_temperature_c": result["max_temperature_c"],
                     "converged_to_0_5_pct_range": result["converged"]})
    OUT_METRICS.mkdir(parents=True, exist_ok=True)
    OUT_FIGURES.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_METRICS / "lfp_16s_active_passive_balancing.csv"
    json_path = OUT_METRICS / "lfp_16s_active_passive_balancing.json"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    report = {
        "status": "RESEARCH_SIMULATION",
        "topology": "generic shared-capacitor-bank cell selection and equalization abstraction",
        "comparison": "resistor bleed with matched SOC thresholds and initial state",
        "configuration": {"cells": 16, "initial_soc_fraction": INITIAL_SOC.tolist(),
                          "capacity_ah": 100.0, "time_step_s": DT_S,
                          "maximum_simulated_hours": MAX_HOURS,
                          "active_max_transfer_current_a": active.DEFAULT_MAX_TRANSFER_CURRENT_A,
                          "active_equivalent_resistance_ohm": active.DEFAULT_EQUIVALENT_RESISTANCE_OHM,
                          "start_delta_soc": active.DEFAULT_START_DELTA_SOC,
                          "stop_delta_soc": active.DEFAULT_STOP_DELTA_SOC,
                          "max_temperature_c": active.DEFAULT_MAX_TEMP_C,
                          "passive_bleed_resistance_ohm": 100.0},
        "models": {"active": rows[0], "passive": rows[1]},
        "limitations": [
            "Both strategies use the passive model's illustrative linear SOC-voltage relation, not calibrated LFP OCV data.",
            "The active stage is a behavioral shared-capacitor charge-transfer abstraction, not a switched circuit or component design.",
            "The active transfer-current limit and equivalent resistance are assumed, not selected from a rated device.",
            "No converter switching, capacitor ripple, parasitic, control stability, EMI, or cell electrochemical dynamics are modeled.",
            "Results compare this one initial SOC vector and ideal charge-only condition; they are not universal efficiency claims.",
        ],
        "raw_outputs": {"csv": str(csv_path.relative_to(ROOT))},
    }
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    for ax, strategy, result in zip(axes, ("active abstraction", "passive resistor"),
                                    (active_result, passive_result), strict=True):
        ax.bar(np.arange(1, 17), 100 * result["final_soc"])
        ax.set(title=f"{strategy}\n{result['elapsed_s']/3600:.1f} h simulated",
               xlabel="Cell index", ylabel="Final SOC (%)", ylim=(60, 100))
        ax.grid(axis="y", alpha=.25)
    figure.suptitle("Balancing comparison under matched initial SOC and stop criterion")
    figure.tight_layout()
    figure_path = OUT_FIGURES / "lfp_16s_active_passive_balancing.png"
    figure.savefig(figure_path, dpi=160)
    plt.close(figure)
    print(pd.DataFrame(rows).to_string(index=False))
    print("Report:", json_path)
    print("Figure:", figure_path)
    # A non-converged topology/horizon is a valid negative experiment result.
    # The CSV reports convergence explicitly for later design decisions.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
