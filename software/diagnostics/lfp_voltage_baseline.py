"""Threshold and persistence baseline for 16-cell voltage deviation data."""

from dataclasses import dataclass
import numpy as np


CELL_COUNT = 16


@dataclass(frozen=True)
class BaselineResult:
    status: str
    suspected_cell: int | None
    first_detection_index: int | None
    candidates: tuple[int, ...]


def evaluate_voltage_deviation(cell_voltages_v, threshold_v=0.015, persistence_samples=5):
    """Return DETECTED only for a unique persistent cell; otherwise UNKNOWN/AMBIGUOUS."""
    try:
        values = np.asarray(cell_voltages_v, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("cell_voltages_v must be a finite 2D numeric array") from exc
    if values.ndim != 2 or values.shape[1] != CELL_COUNT or values.shape[0] == 0:
        raise ValueError("cell_voltages_v must have shape (samples, 16)")
    if not np.all(np.isfinite(values)) or np.any(values <= 0):
        raise ValueError("all cell voltages must be finite and positive")
    if not np.isfinite(threshold_v) or threshold_v <= 0:
        raise ValueError("threshold_v must be finite and positive")
    if isinstance(persistence_samples, bool) or not isinstance(persistence_samples, int) or persistence_samples < 1:
        raise ValueError("persistence_samples must be a positive integer")

    deviations = np.median(values, axis=1, keepdims=True) - values
    consecutive = np.zeros(CELL_COUNT, dtype=int)
    for row_index, row in enumerate(deviations):
        consecutive = np.where(row >= threshold_v, consecutive + 1, 0)
        candidates = tuple(int(i + 1) for i in np.flatnonzero(consecutive >= persistence_samples))
        if candidates:
            if len(candidates) == 1:
                return BaselineResult("DETECTED", candidates[0], row_index, candidates)
            return BaselineResult("AMBIGUOUS", None, row_index, candidates)
    return BaselineResult("UNKNOWN", None, None, ())
