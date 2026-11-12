"""Mode-level BDU state abstraction; distinct from contactor protection logic."""

from dataclasses import asdict, dataclass
from enum import Enum


class BDUOperatingMode(str, Enum):
    DRIVE = "DRIVE"
    CHARGE = "CHARGE"
    PARK = "PARK"
    FAULT = "FAULT"
    EMERGENCY_DISCONNECT = "EMERGENCY_DISCONNECT"


@dataclass(frozen=True)
class BDUOperatingReading:
    mode: str
    reason: str
    emergency_latched: bool
    mode_selected: bool

    def to_dict(self):
        return asdict(self)


class BDUOperatingModeController:
    """Resolve requested operating modes with fault/emergency priority."""

    REQUESTABLE = {BDUOperatingMode.DRIVE, BDUOperatingMode.CHARGE, BDUOperatingMode.PARK}

    def __init__(self):
        self.mode = BDUOperatingMode.PARK
        self.emergency_latched = False

    def update(
        self,
        requested_mode: str | BDUOperatingMode = BDUOperatingMode.PARK,
        *,
        protection_fault: bool = False,
        emergency_disconnect: bool = False,
        reset_emergency: bool = False,
    ) -> BDUOperatingReading:
        try:
            requested = BDUOperatingMode(requested_mode)
        except ValueError as exc:
            raise ValueError("requested_mode must be DRIVE, CHARGE, or PARK") from exc
        if requested not in self.REQUESTABLE:
            raise ValueError("FAULT and EMERGENCY_DISCONNECT are state outcomes, not requests")
        if any(type(flag) is not bool for flag in (protection_fault, emergency_disconnect, reset_emergency)):
            raise ValueError("state inputs must be booleans")

        if emergency_disconnect:
            self.emergency_latched = True
            self.mode = BDUOperatingMode.EMERGENCY_DISCONNECT
            reason = "EMERGENCY_DISCONNECT_REQUEST"
        elif self.emergency_latched:
            if reset_emergency and not protection_fault:
                self.emergency_latched = False
                self.mode = BDUOperatingMode.PARK
                reason = "EMERGENCY_RESET_TO_PARK"
            else:
                self.mode = BDUOperatingMode.EMERGENCY_DISCONNECT
                reason = "EMERGENCY_LATCHED"
        elif protection_fault:
            self.mode = BDUOperatingMode.FAULT
            reason = "PROTECTION_FAULT"
        else:
            self.mode = requested
            reason = "MODE_REQUEST_ACCEPTED"

        return BDUOperatingReading(
            mode=self.mode.value,
            reason=reason,
            emergency_latched=self.emergency_latched,
            mode_selected=self.mode in self.REQUESTABLE,
        )
