import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "software" / "diagnostics" / "lfp_voltage_baseline.py"
SPEC = importlib.util.spec_from_file_location("baseline_voltage", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_healthy_equal_cells_do_not_raise_an_anomaly():
    readings = np.full((8, 16), 3.3)
    assert MODULE.evaluate_voltage_deviation(readings).status == "UNKNOWN"


def test_persistent_single_cell_deviation_localizes_only_after_persistence():
    readings = np.full((6, 16), 3.3)
    readings[:, 7] = 3.27
    result = MODULE.evaluate_voltage_deviation(readings, threshold_v=0.015, persistence_samples=5)
    assert result.status == "DETECTED"
    assert result.suspected_cell == 8
    assert result.first_detection_index == 4


def test_transient_deviation_does_not_localize():
    readings = np.full((7, 16), 3.3)
    readings[2, 7] = 3.25
    assert MODULE.evaluate_voltage_deviation(readings).status == "UNKNOWN"


def test_two_persistent_candidates_are_ambiguous():
    readings = np.full((5, 16), 3.3)
    readings[:, 2] = 3.27
    readings[:, 9] = 3.26
    result = MODULE.evaluate_voltage_deviation(readings, persistence_samples=5)
    assert result.status == "AMBIGUOUS"
    assert result.suspected_cell is None
    assert result.candidates == (3, 10)


@pytest.mark.parametrize("readings", [np.ones(16), np.full((2, 15), 3.3), np.full((2, 16), np.nan)])
def test_invalid_measurement_shapes_and_values_are_rejected(readings):
    with pytest.raises(ValueError):
        MODULE.evaluate_voltage_deviation(readings)
