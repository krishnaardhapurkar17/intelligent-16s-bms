"""Validated per-cell configuration for the 16S simulation models."""

from dataclasses import dataclass, replace
import math


CELL_COUNT = 16


@dataclass(frozen=True)
class CellConfiguration:
    initial_soc: float = 0.90  # fraction in [0, 1]
    capacity_ah: float = 100.0
    resistance_ohm: float = 0.0005

    def __post_init__(self):
        for name, value in (("initial_soc", self.initial_soc),
                            ("capacity_ah", self.capacity_ah),
                            ("resistance_ohm", self.resistance_ohm)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number")
        if not 0.0 <= self.initial_soc <= 1.0:
            raise ValueError("initial_soc must be between 0 and 1")
        if self.capacity_ah <= 0 or self.resistance_ohm <= 0:
            raise ValueError("capacity_ah and resistance_ohm must be positive")


@dataclass(frozen=True)
class PackConfiguration:
    cells: tuple[CellConfiguration, ...]

    def __post_init__(self):
        if len(self.cells) != CELL_COUNT:
            raise ValueError(f"16S pack configuration requires exactly {CELL_COUNT} cells")
        if not all(isinstance(cell, CellConfiguration) for cell in self.cells):
            raise ValueError("every pack entry must be a CellConfiguration")

    @classmethod
    def uniform(cls, initial_soc=0.90, capacity_ah=100.0, resistance_ohm=0.0005):
        cell = CellConfiguration(initial_soc, capacity_ah, resistance_ohm)
        return cls((cell,) * CELL_COUNT)

    def with_cell(self, cell_index: int, **changes):
        """Return a copy with one independently configured 1-based cell."""
        if isinstance(cell_index, bool) or not isinstance(cell_index, int) or not 1 <= cell_index <= CELL_COUNT:
            raise ValueError("cell_index must be 1 through 16")
        cells = list(self.cells)
        cells[cell_index - 1] = replace(cells[cell_index - 1], **changes)
        return PackConfiguration(tuple(cells))

    def values(self, attribute: str) -> tuple[float, ...]:
        if attribute not in {"initial_soc", "capacity_ah", "resistance_ohm"}:
            raise ValueError(f"unsupported cell parameter: {attribute}")
        return tuple(getattr(cell, attribute) for cell in self.cells)
