import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
PACK_MODEL_DIR = PROJECT_ROOT / "models" / "pack-model"
if str(PACK_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(PACK_MODEL_DIR))
DIAGNOSTICS_DIR = PROJECT_ROOT / "software" / "diagnostics"
if str(DIAGNOSTICS_DIR) not in sys.path:
    sys.path.insert(0, str(DIAGNOSTICS_DIR))

import pytest

from software.interfaces.message_schema import BMSMessage, Quality
from software.interfaces.command_authorization import CommandAuthorizer
from software.lifecycle.battery_passport import BatteryPassport
from cell_configuration import CellConfiguration, PackConfiguration
from lfp_voltage_baseline import evaluate_voltage_deviation


def test_pack_configuration_has_sixteen_independent_cells():
    baseline = PackConfiguration.uniform()
    configured = (baseline
                  .with_cell(3, initial_soc=0.72)
                  .with_cell(8, capacity_ah=80.0)
                  .with_cell(12, resistance_ohm=0.0008))
    assert len(configured.cells) == 16
    assert configured.values("initial_soc")[2] == 0.72
    assert configured.values("capacity_ah")[7] == 80.0
    assert configured.values("resistance_ohm")[11] == 0.0008
    assert configured.values("initial_soc")[7] == 0.90
    assert baseline.values("capacity_ah")[7] == 100.0


def test_pack_configuration_rejects_wrong_cell_count_and_invalid_values():
    with pytest.raises(ValueError):
        PackConfiguration((CellConfiguration(),) * 15)
    with pytest.raises(ValueError):
        CellConfiguration(initial_soc=1.1)
    with pytest.raises(ValueError):
        CellConfiguration(capacity_ah=0)


def test_voltage_baseline_reports_healthy_as_unknown():
    healthy = [[3.2] * 16 for _ in range(8)]
    result = evaluate_voltage_deviation(healthy, threshold_v=0.015, persistence_samples=3)
    assert result.status == "UNKNOWN"
    assert result.suspected_cell is None


def test_voltage_baseline_localizes_single_persistent_deviation():
    readings = [[3.2] * 16 for _ in range(5)]
    for row in readings:
        row[7] = 3.16
    result = evaluate_voltage_deviation(readings, threshold_v=0.015, persistence_samples=3)
    assert result.status == "DETECTED"
    assert result.suspected_cell == 8
    assert result.first_detection_index == 2


def test_voltage_baseline_reports_ambiguous_localization():
    readings = [[3.2] * 16 for _ in range(5)]
    for row in readings:
        row[3] = 3.16
        row[11] = 3.16
    result = evaluate_voltage_deviation(readings, threshold_v=0.015, persistence_samples=3)
    assert result.status == "AMBIGUOUS"
    assert result.suspected_cell is None
    assert result.candidates == (4, 12)


def test_message_round_trip_and_freshness():
    message = BMSMessage("cell_voltage", 100.0, Quality.VALID.value, 3.25, "V", 16, 0.001)
    assert BMSMessage.from_dict(message.to_dict()) == message
    assert message.freshness(now_s=101, max_age_s=2) == "FRESH"
    assert message.freshness(now_s=103, max_age_s=2) == "STALE"


@pytest.mark.parametrize("kwargs", [
    {"cell_index": 0}, {"cell_index": 17}, {"timestamp_s": float("nan")},
    {"quality": "MAYBE"}, {"unit": ""}, {"scale": 0}, {"value": float("inf")},
])
def test_message_rejects_invalid_contract(kwargs):
    data = dict(message_type="cell_voltage", timestamp_s=10, quality="VALID", value=3.2, unit="V")
    data.update(kwargs)
    with pytest.raises(ValueError):
        BMSMessage(**data)


def test_command_authorization_grants_and_rejects():
    auth = CommandAuthorizer({"operator": "operator", "service": "service"},
                             {"start": {"operator"}, "update": {"service"}})
    assert auth.authorize("start", "operator", "operator").state == "AUTHORIZED"
    assert auth.authorize("update", "operator", "operator").reason == "ROLE_NOT_AUTHORIZED"
    assert auth.authorize("start", "operator", "wrong").reason == "INVALID_CREDENTIAL"
    assert auth.authorize("missing", "service", "service").reason == "UNKNOWN_COMMAND"


def test_lifecycle_records_replay_in_order(tmp_path):
    log = BatteryPassport(tmp_path / "passport.jsonl")
    first = {"timestamp_s": 1, "event_type": "run_started", "configuration": {"seed": 7}, "faults": [], "degradation": {}}
    second = {"timestamp_s": 2, "event_type": "fault_injected", "configuration": {"seed": 7}, "faults": ["cell_4"], "degradation": {"capacity_soh": 0.98}}
    log.append(first)
    log.append(second)
    assert log.replay() == [first, second]
    stored = json.loads((tmp_path / "passport.jsonl").read_text().splitlines()[0])
    assert {key: stored[key] for key in first} == first
    assert stored["_integrity"]["algorithm"] == "sha256-chain-v1"


def test_lifecycle_replay_rejects_corrupt_record(tmp_path):
    path = tmp_path / "passport.jsonl"
    path.write_text('{"event_type":\n', encoding="utf-8")
    with pytest.raises(ValueError, match="line 1"):
        BatteryPassport(path).replay()


def test_lifecycle_replay_detects_tampered_hash_chain(tmp_path):
    path = tmp_path / "passport.jsonl"
    log = BatteryPassport(path)
    first = {"timestamp_s": 1, "event_type": "run_started", "configuration": {"seed": 7}, "faults": [], "degradation": {}}
    log.append(first)
    stored = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    stored["configuration"]["seed"] = 8
    path.write_text(json.dumps(stored) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="record hash mismatch"):
        log.replay()
