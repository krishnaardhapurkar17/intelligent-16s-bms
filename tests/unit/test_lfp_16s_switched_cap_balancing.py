import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "models" / "balancing" / "lfp_16s_switched_cap_active_balancing.py"
SPEC = importlib.util.spec_from_file_location("active_balancing", PATH)
MODEL = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODEL
SPEC.loader.exec_module(MODEL)


def test_adjacent_transfer_conserves_charge_and_reports_nonnegative_loss():
    balancer = MODEL.SwitchedCapacitorBalancer()
    initial = np.array([0.9, 0.7] + [0.8] * 14)
    final, transfer = balancer.step(initial, dt_s=60)
    assert transfer.source_cell == 1 and transfer.target_cell == 2
    assert np.sum(final) == pytest.approx(np.sum(initial))
    assert transfer.current_a <= balancer.max_current_a
    assert transfer.loss_energy_wh >= 0
    assert final[0] < initial[0] and final[1] > initial[1]


@pytest.mark.parametrize("kwargs", [
    {"bdu_closed": False}, {"charge_mode": False}, {"protection_fault": True},
    {"sensor_valid": [False] + [True] * 15},
    {"temperature_c": [45.0] + [25.0] * 15},
])
def test_safety_conditions_inhibit_active_transfer(kwargs):
    balancer = MODEL.SwitchedCapacitorBalancer()
    initial = np.array([0.9, 0.7] + [0.8] * 14)
    final, transfer = balancer.step(initial, dt_s=60, **kwargs)
    assert transfer.current_a == 0
    assert np.array_equal(final, initial)


def test_invalid_pack_soc_is_rejected():
    with pytest.raises(ValueError):
        MODEL.SwitchedCapacitorBalancer().step([0.5] * 15)


def test_run_active_conserves_charge_and_reduces_soc_range():
    initial = np.linspace(0.90, 0.75, MODEL.CELL_COUNT)
    result = MODEL.run_active(initial, max_hours=5, dt_s=60)
    assert result["charge_conservation_error_ah"] == pytest.approx(0, abs=1e-9)
    assert result["range_final"] < result["range_initial"]
    assert result["loss_energy_wh"] >= 0
