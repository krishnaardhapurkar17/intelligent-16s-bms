import importlib.util
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "models" / "balancing" / "lfp_16s_passive_balancing.py"
SPEC = importlib.util.spec_from_file_location("passive_balancing_model", MODULE_PATH)
MODEL = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODEL
SPEC.loader.exec_module(MODEL)


def test_passive_bleed_current_power_energy_and_soc_are_consistent():
    cells = MODEL.CellBank([85.0] * MODEL.CELL_COUNT)
    active = [True] + [False] * (MODEL.CELL_COUNT - 1)
    voltage = cells.voltage[0]
    expected_current = voltage / MODEL.BALANCING_RESISTANCE_OHM
    expected_power = voltage * expected_current
    dt_s = 60.0

    cells.update(active, dt_s)

    assert cells.balancing_current[0] == expected_current
    assert cells.balancing_power[0] == expected_power
    assert abs(cells.dissipated_energy_wh[0] - expected_power * dt_s / 3600) < 1e-12
    expected_soc_drop = expected_current * dt_s / (3600 * MODEL.CAPACITY_AH) * 100
    assert abs(cells.soc[0] - (85.0 - expected_soc_drop)) < 1e-12
    assert (cells.dissipated_energy_wh[1:] == 0).all()


def test_balancing_eligibility_enforces_bdu_charge_fault_and_temperature():
    balancer = MODEL.PassiveBalancer()
    voltages = MODEL.soc_to_voltage(np.array([85.0] * 7 + [80.0] + [85.0] * 8))
    temperatures = [25.0] * MODEL.CELL_COUNT

    eligible = balancer.update_eligibility(voltages, temperatures, "CLOSED", True, False)
    assert not eligible[7]
    assert eligible[:7].all() and eligible[8:].all()

    for bdu_state, charge_mode, fault in (
        ("OPEN", True, False), ("CLOSED", False, False), ("CLOSED", True, True)
    ):
        blocked = balancer.update_eligibility(voltages, temperatures, bdu_state, charge_mode, fault)
        assert not blocked.any()

    temperatures[0] = MODEL.MAX_BALANCING_TEMP_C
    thermal = balancer.update_eligibility(voltages, temperatures, "CLOSED", True, False)
    assert not thermal[0]
    assert thermal[1:7].all() and not thermal[7] and thermal[8:].all()


def test_run_scenario_records_samples_and_respects_global_interlocks(monkeypatch):
    monkeypatch.setattr(MODEL, "SIMULATION_DURATION_S", 4)
    monkeypatch.setattr(MODEL, "TIME_STEP_S", 1.0)
    soc = [85.0] * 7 + [80.0] + [85.0] * 8

    normal = MODEL.run_scenario("short", soc)
    assert len(normal["history"]) == 32
    assert not normal["final_balancing_active"][7]
    assert normal["final_balancing_active"][0]
    assert all("Dissipated_Energy_Wh" in item for item in normal["history"])

    for kwargs in ({"bdu_state": "OPEN"}, {"charge_mode": False},
                   {"protection_fault": True}):
        blocked = MODEL.run_scenario("blocked", soc, **kwargs)
        assert not blocked["final_balancing_active"].any()

    hot = np.full(MODEL.CELL_COUNT, MODEL.AMBIENT_TEMP_C)
    hot[0] = MODEL.MAX_BALANCING_TEMP_C
    monkeypatch.setattr(MODEL, "SIMULATION_DURATION_S", 1)
    thermal = MODEL.run_scenario("hot", soc, initial_temperature=hot)
    assert not thermal["final_balancing_active"][0]


def test_json_serializer_handles_numpy_and_paths_and_rejects_other_values(tmp_path):
    payload = {"array": np.asarray([1, 2]), "number": np.int64(3), "path": tmp_path}
    encoded = json.dumps(payload, default=MODEL.json_serializer)
    assert json.loads(encoded) == {"array": [1, 2], "number": 3, "path": str(tmp_path)}
    with np.testing.assert_raises(TypeError):
        MODEL.json_serializer(object())


def test_passive_balancing_scenario_runner_writes_passing_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    MODEL.main()
    report = tmp_path / "results" / "metrics" / "lfp_16s_passive_balancing_summary.json"
    csv_path = tmp_path / "results" / "metrics" / "lfp_16s_passive_balancing.csv"
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["overall"] == "PASS"
    assert len(data["scenarios"]) == 5
    assert data["validation"] and all(data["validation"].values())
    assert csv_path.is_file() and csv_path.stat().st_size > 0
