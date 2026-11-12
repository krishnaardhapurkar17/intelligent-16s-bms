import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from software.protection.lfp_16s_state_of_safety import SafetyInputs, evaluate_state_of_safety


def base(**changes):
    values = dict(bdu_state="CLOSED", pmu_quality="VALID", sensor_quality="VALID",
                  thermal_state="NORMAL", insulation_state="NORMAL", diagnostic_state="CLEAR")
    values.update(changes)
    return SafetyInputs(**values)


def test_safety_summary_normal_and_warning():
    assert evaluate_state_of_safety(base()).state == "NORMAL"
    assert evaluate_state_of_safety(base(thermal_state="WARNING")).state == "WARNING"


def test_safety_summary_fault_precedes_missing_measurements():
    result = evaluate_state_of_safety(base(bdu_state="FAULT", pmu_quality="UNAVAILABLE"))
    assert result.state == "FAULT"
    assert "BDU_FAULT" in result.reasons


def test_safety_summary_unknown_for_invalid_or_unavailable_inputs():
    assert evaluate_state_of_safety(base(pmu_quality="UNAVAILABLE")).state == "UNKNOWN"
    assert evaluate_state_of_safety(base(thermal_state="UNKNOWN")).state == "UNKNOWN"


def test_safety_summary_includes_insulation_and_degradation_warnings():
    assert evaluate_state_of_safety(base(insulation_state="CRITICAL")).state == "FAULT"
    assert evaluate_state_of_safety(base(diagnostic_state="DEGRADATION_INDICATED")).state == "WARNING"
