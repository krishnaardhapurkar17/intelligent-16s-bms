import importlib.util
from pathlib import Path
import sys

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "models" / "pack-model" / "evaluate_fault_baselines.py"
SPEC = importlib.util.spec_from_file_location("fault_baseline_evaluator", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_voltage_only_baseline_detects_but_cannot_classify_fault_type():
    rows = []
    for scenario, faulty_cell, enhanced in (
        ("Healthy", None, "No anomaly detected"),
        ("Cell 8 resistance growth", 8, "Possible resistance degradation"),
        ("Cell 8 sensor bias", 8, "Possible voltage sensor bias"),
    ):
        for cell in range(1, 17):
            is_fault = cell == faulty_cell
            rows.append({"Scenario": scenario, "Cell": cell,
                         "Voltage_Anomaly": is_fault,
                         "Resistance_Anomaly": scenario.endswith("resistance growth") and is_fault,
                         "Classification": enhanced if is_fault else "No anomaly detected"})
    result = MODULE.evaluate(pd.DataFrame(rows))
    assert result["voltage_only_baseline"]["tp"] == 2
    assert result["voltage_only_baseline"]["fp"] == 0
    assert result["multi_signal_classifier"]["recall"] == 1.0
    assert result["fault_type_correct"] == result["fault_type_total"] == 2


def test_unrecognized_scenario_is_rejected():
    data = pd.DataFrame([{"Scenario": "Other", "Cell": 1,
                          "Voltage_Anomaly": False, "Resistance_Anomaly": False,
                          "Classification": "No anomaly detected"}])
    with pytest.raises(ValueError, match="unexpected scenarios"):
        MODULE.evaluate(data)
