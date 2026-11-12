"""Advisory state-of-safety summary for the simulation model."""

from dataclasses import asdict, dataclass
from enum import Enum


class SafetyState(str, Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    FAULT = "FAULT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class SafetyInputs:
    bdu_state: str
    pmu_quality: str
    sensor_quality: str
    thermal_state: str
    insulation_state: str
    diagnostic_state: str


@dataclass(frozen=True)
class SafetyReading:
    state: str
    reasons: tuple[str, ...]
    advisory_only: bool = True

    def to_dict(self):
        return asdict(self)


def evaluate_state_of_safety(inputs: SafetyInputs) -> SafetyReading:
    """Summarize modeled inputs; this does not command or replace BDU protection."""
    allowed = {
        "bdu_state": {"OPEN", "PRECHARGE", "CLOSED", "FAULT", "RECOVERY"},
        "pmu_quality": {"VALID", "WARNING", "INVALID", "UNAVAILABLE"},
        "sensor_quality": {"VALID", "WARNING", "INVALID", "UNAVAILABLE"},
        "thermal_state": {"NORMAL", "WARNING", "CRITICAL", "UNKNOWN"},
        "insulation_state": {"NORMAL", "WARNING", "CRITICAL", "UNKNOWN"},
        "diagnostic_state": {"CLEAR", "DEGRADATION_INDICATED", "MULTIPLE_INDICATORS", "UNKNOWN"},
    }
    unknown_fields = [name for name, values in allowed.items() if getattr(inputs, name) not in values]
    if unknown_fields:
        return SafetyReading(SafetyState.UNKNOWN.value,
                             tuple(f"INVALID_{name.upper()}" for name in unknown_fields))

    faults = []
    if inputs.bdu_state == "FAULT":
        faults.append("BDU_FAULT")
    if inputs.thermal_state == "CRITICAL":
        faults.append("THERMAL_CRITICAL")
    if inputs.insulation_state == "CRITICAL":
        faults.append("INSULATION_CRITICAL")
    if faults:
        return SafetyReading(SafetyState.FAULT.value, tuple(faults))

    unavailable = []
    if inputs.pmu_quality in {"INVALID", "UNAVAILABLE"}:
        unavailable.append("PMU_QUALITY_NOT_VALID")
    if inputs.sensor_quality in {"INVALID", "UNAVAILABLE"}:
        unavailable.append("SENSOR_QUALITY_NOT_VALID")
    if inputs.thermal_state == "UNKNOWN":
        unavailable.append("THERMAL_STATE_UNKNOWN")
    if inputs.insulation_state == "UNKNOWN":
        unavailable.append("INSULATION_STATE_UNKNOWN")
    if inputs.diagnostic_state == "UNKNOWN":
        unavailable.append("DIAGNOSTIC_STATE_UNKNOWN")
    if unavailable:
        return SafetyReading(SafetyState.UNKNOWN.value, tuple(unavailable))

    warnings = []
    if inputs.pmu_quality == "WARNING":
        warnings.append("PMU_QUALITY_WARNING")
    if inputs.sensor_quality == "WARNING":
        warnings.append("SENSOR_QUALITY_WARNING")
    if inputs.thermal_state == "WARNING":
        warnings.append("THERMAL_WARNING")
    if inputs.insulation_state == "WARNING":
        warnings.append("INSULATION_WARNING")
    if inputs.diagnostic_state in {"DEGRADATION_INDICATED", "MULTIPLE_INDICATORS"}:
        warnings.append(inputs.diagnostic_state)
    if warnings:
        return SafetyReading(SafetyState.WARNING.value, tuple(warnings))
    return SafetyReading(SafetyState.NORMAL.value, ("NO_MODELED_WARNING_OR_FAULT",))
