import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from software.protection.lfp_16s_bdu_operating_mode import BDUOperatingModeController


def test_required_modes_are_represented():
    controller = BDUOperatingModeController()
    for mode in ("DRIVE", "CHARGE", "PARK"):
        assert controller.update(mode).mode == mode
    assert controller.update("DRIVE", protection_fault=True).mode == "FAULT"
    assert controller.update("CHARGE", emergency_disconnect=True).mode == "EMERGENCY_DISCONNECT"


def test_protection_fault_overrides_request_and_emergency_is_latched():
    controller = BDUOperatingModeController()
    assert controller.update("DRIVE", protection_fault=True).mode == "FAULT"
    assert controller.update("DRIVE").mode == "DRIVE"

    controller.update("PARK", emergency_disconnect=True)
    held = controller.update("DRIVE")
    assert held.mode == "EMERGENCY_DISCONNECT"
    assert held.emergency_latched

    blocked_reset = controller.update("DRIVE", protection_fault=True, reset_emergency=True)
    assert blocked_reset.mode == "EMERGENCY_DISCONNECT"
    reset = controller.update("DRIVE", reset_emergency=True)
    assert reset.mode == "PARK"
    assert not reset.emergency_latched


def test_outcome_states_cannot_be_requested():
    controller = BDUOperatingModeController()
    with pytest.raises(ValueError):
        controller.update("FAULT")
    with pytest.raises(ValueError):
        controller.update("READY")


def test_identical_input_sequences_produce_identical_mode_transitions():
    sequence = [
        {"requested_mode": "DRIVE"},
        {"requested_mode": "CHARGE", "protection_fault": True},
        {"requested_mode": "PARK", "emergency_disconnect": True},
        {"requested_mode": "DRIVE"},
        {"requested_mode": "CHARGE", "reset_emergency": True},
    ]
    outcomes = []
    for _ in range(2):
        controller = BDUOperatingModeController()
        outcomes.append([controller.update(**inputs).to_dict() for inputs in sequence])
    assert outcomes[0] == outcomes[1]
    assert [row["mode"] for row in outcomes[0]] == [
        "DRIVE", "FAULT", "EMERGENCY_DISCONNECT", "EMERGENCY_DISCONNECT", "PARK"
    ]
