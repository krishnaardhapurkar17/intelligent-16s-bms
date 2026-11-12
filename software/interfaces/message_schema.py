"""Transport independent simulation message contract for future CAN mapping."""

from dataclasses import asdict, dataclass
from enum import Enum
import math
import time
from typing import Any


CELL_COUNT = 16
SCHEMA_VERSION = "1.0"


class Quality(str, Enum):
    VALID = "VALID"
    WARNING = "WARNING"
    INVALID = "INVALID"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class BMSMessage:
    message_type: str
    timestamp_s: float
    quality: str
    value: float | int | bool | str | None
    unit: str
    cell_index: int | None = None
    scale: float = 1.0
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self):
        if not isinstance(self.message_type, str) or not self.message_type.strip():
            raise ValueError("message_type must not be empty")
        if (
            isinstance(self.timestamp_s, bool)
            or not isinstance(self.timestamp_s, (int, float))
            or not math.isfinite(self.timestamp_s)
            or self.timestamp_s < 0
        ):
            raise ValueError("timestamp_s must be a finite nonnegative Unix timestamp")
        if self.quality not in {item.value for item in Quality}:
            raise ValueError("quality must be VALID, WARNING, INVALID, or UNAVAILABLE")
        if not isinstance(self.unit, str) or not self.unit.strip():
            raise ValueError("unit must be explicit, use '1' for dimensionless values")
        if not math.isfinite(self.scale) or self.scale <= 0:
            raise ValueError("scale must be finite and positive")
        if self.cell_index is not None and (
            isinstance(self.cell_index, bool)
            or not isinstance(self.cell_index, int)
            or not 1 <= self.cell_index <= CELL_COUNT
        ):
            raise ValueError("cell_index must be 1 through 16")
        if isinstance(self.value, (float, int)) and not isinstance(self.value, bool):
            if not math.isfinite(float(self.value)):
                raise ValueError("numeric value must be finite")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BMSMessage":
        return cls(**data)

    def freshness(self, now_s: float | None = None, max_age_s: float = 2.0) -> str:
        """Return FRESH/STALE; caller should treat stale values as unusable."""
        now = time.time() if now_s is None else float(now_s)
        if (
            not math.isfinite(now)
            or isinstance(max_age_s, bool)
            or not isinstance(max_age_s, (int, float))
            or not math.isfinite(max_age_s)
            or max_age_s < 0
        ):
            raise ValueError("now_s must be finite and max_age_s nonnegative")
        age = now - self.timestamp_s
        return "FRESH" if 0 <= age <= max_age_s else "STALE"
