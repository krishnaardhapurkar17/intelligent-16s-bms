"""Research estimators backed by the supplied Battery Guardian models.

The SOC network was trained on LG NMC cells; SOH/RUL ensembles were trained
on NASA NMC/LCO cells. Calls for LFP are rejected to prevent domain-mismatched
AI outputs from being treated as valid estimates for this LFP project.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping

import numpy as np

from software.interfaces.message_schema import BMSMessage, Quality


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = PROJECT_ROOT / "models" / "ai"
SOC_FEATURES = ("voltage_v", "current_a", "temperature_c")
SOH_FEATURES = (
    "cycle",
    "Re",
    "Rct",
    "ambient_temperature",
    "capacity_fade",
    "delta_Capacity",
)
RUL_FEATURES = (
    "cycle",
    "SOH",
    "Re",
    "Rct",
    "ambient_temperature",
    "capacity_fade",
    "delta_Capacity",
)
LFP_SOH_FEATURES = (
    "cumulative_cycles",
    "pulse_resistance_ohm_mean",
    "pulse_soc_count",
)
LFP_RUL_FEATURES = (
    "cumulative_cycles",
    "soh_pct",
    "soh_fade_pct_per_1000_cycles",
)


class UnsupportedChemistryError(ValueError):
    """Raised when an estimator is asked to predict outside its training domain."""


@dataclass(frozen=True)
class AIEstimate:
    value: float
    unit: str
    model_id: str
    training_domain: str
    evidence_status: str = "RESEARCH_ONLY"

    def to_message(self, *, timestamp_s: float, cell_index: int | None = None) -> BMSMessage:
        """Serialize AI output as a warning-quality message, never as validated data."""
        return BMSMessage(
            message_type=f"AI_{self.model_id.replace('-', '_')}",
            timestamp_s=timestamp_s,
            quality=Quality.WARNING.value,
            value=self.value,
            unit=self.unit,
            cell_index=cell_index,
        )


def _chemistry_key(chemistry: str) -> str:
    if not isinstance(chemistry, str) or not chemistry.strip():
        raise ValueError("chemistry must be a non-empty string")
    return "".join(ch for ch in chemistry.upper() if ch.isalnum())


def _require_supported_chemistry(chemistry: str, supported: set[str]) -> None:
    key = _chemistry_key(chemistry)
    if key not in supported:
        raise UnsupportedChemistryError(
            f"Model training chemistry does not cover {chemistry!r}; "
            f"supported training domains are {', '.join(sorted(supported))}."
        )


def _feature_vector(features: Mapping[str, float], names: tuple[str, ...]) -> np.ndarray:
    if not isinstance(features, Mapping):
        raise TypeError("features must be a mapping keyed by the documented feature names")
    missing = [name for name in names if name not in features]
    if missing:
        raise ValueError(f"missing model features: {', '.join(missing)}")
    vector = np.asarray([features[name] for name in names], dtype=np.float64)
    if vector.shape != (len(names),) or not np.isfinite(vector).all():
        raise ValueError("model features must be finite numeric scalars")
    return vector


class _PortableEnsemble:
    """Execute a lossless tree/weight export from MATLAB fitrensemble."""

    def __init__(self, model_dir: Path, filename: str):
        path = model_dir / filename
        with path.open(encoding="utf-8") as stream:
            self.data = json.load(stream)
        if self.data.get("format_version") != 1:
            raise ValueError(f"unsupported ensemble export format in {path.name}")
        self.features = tuple(self.data["features"])
        self.trees = self.data["trees"]
        self.weights = np.asarray(self.data["weights"], dtype=np.float64)
        self.bias = float(self.data["bias"])
        if len(self.trees) != len(self.weights) or not len(self.trees):
            raise ValueError(f"inconsistent tree/weight arrays in {path.name}")

    @staticmethod
    def _predict_tree(tree: dict, sample: np.ndarray) -> float:
        children = tree["children"]
        feature_indices = tree["cut_predictor_index"]
        cut_points = tree["cut_point"]
        node_values = tree["node_mean"]
        node = 0
        while children[node][0] != 0:
            feature = int(feature_indices[node]) - 1  # MATLAB indices are one-based.
            if feature < 0 or feature >= len(sample):
                raise ValueError("tree contains an invalid predictor index")
            # MATLAB continuous regression-tree splits send values below the cut left.
            node = int(children[node][0] if sample[feature] < cut_points[node]
                       else children[node][1]) - 1
        return float(node_values[node])

    def predict(self, values: np.ndarray) -> float:
        weighted = sum(
            weight * self._predict_tree(tree, values)
            for weight, tree in zip(self.weights, self.trees, strict=True)
        )
        value = self.bias + float(weighted)
        if not np.isfinite(value):
            raise ValueError("ensemble produced a non-finite prediction")
        return value


class BatteryAIEstimators:
    """Lazy-loaded inference facade for the supplied SOC, SOH and RUL models."""

    def __init__(self, *, model_dir: Path | None = None):
        self.model_dir = MODEL_DIR if model_dir is None else Path(model_dir)
        self._soh = _PortableEnsemble(self.model_dir, "soh_ensemble.json")
        self._rul = _PortableEnsemble(self.model_dir, "rul_ensemble.json")
        self._soc_model = None
        self._soc_norm = None
        self._soc_buffer: list[list[float]] = []
        self._lfp_soh = None
        self._lfp_rul = None
        self._soc_metadata = json.loads(
            (self.model_dir / "soc_metadata.json").read_text(encoding="utf-8")
        )
        self._soc_norm = json.loads(
            (self.model_dir / "soc_norm_constants.json").read_text(encoding="utf-8")
        )

    def _load_soc_model(self):
        if self._soc_model is None:
            try:
                import tensorflow as tf
            except ImportError as exc:
                raise RuntimeError(
                    "SOC inference requires the optional TensorFlow AI dependencies"
                ) from exc
            self._soc_model = tf.keras.models.load_model(
                self.model_dir / "soc_cnn_lstm.keras", compile=False
            )
        return self._soc_model

    def predict_soc_window(
        self, window: np.ndarray, *, chemistry: str
    ) -> AIEstimate:
        _require_supported_chemistry(chemistry, {"NMC"})
        data = np.asarray(window, dtype=np.float32)
        seq_len = int(self._soc_norm["SEQ_LEN"])
        if data.shape != (seq_len, 3) or not np.isfinite(data).all():
            raise ValueError(f"window must be a finite {seq_len}x3 array [V, A, °C]")
        nc = self._soc_norm
        mins = np.asarray([nc["V_min"], nc["I_min"], nc["T_min"]], dtype=np.float32)
        maxs = np.asarray([nc["V_max"], nc["I_max"], nc["T_max"]], dtype=np.float32)
        normalized = np.clip((data - mins) / (maxs - mins), 0.0, 1.0)
        prediction = self._load_soc_model()(normalized[np.newaxis, ...], training=False)
        value = float(np.clip(np.asarray(prediction).reshape(-1)[0], 0.0, 1.0))
        return AIEstimate(value, "1", "SOC-CNN-LSTM", "LG INR 21700 NMC")

    def update_soc(
        self, *, voltage_v: float, current_a: float, temperature_c: float, chemistry: str
    ) -> AIEstimate | None:
        _require_supported_chemistry(chemistry, {"NMC"})
        sample = np.asarray([voltage_v, current_a, temperature_c], dtype=np.float32)
        if not np.isfinite(sample).all():
            raise ValueError("SOC inputs must be finite")
        self._soc_buffer.append(sample.tolist())
        self._soc_buffer = self._soc_buffer[-int(self._soc_norm["SEQ_LEN"]):]
        if len(self._soc_buffer) < int(self._soc_norm["SEQ_LEN"]):
            return None
        return self.predict_soc_window(np.asarray(self._soc_buffer), chemistry=chemistry)

    def reset_soc(self) -> None:
        self._soc_buffer.clear()

    def predict_soh(self, features: Mapping[str, float], *, chemistry: str) -> AIEstimate:
        if _chemistry_key(chemistry) == "LFP":
            values = _feature_vector(features, LFP_SOH_FEATURES)
            if self._lfp_soh is None:
                self._lfp_soh = _PortableEnsemble(self.model_dir, "lfp_soh_ensemble.json")
            prediction = float(np.clip(self._lfp_soh.predict(values), 0.0, 110.0))
            return AIEstimate(prediction, "%", "SOH-LFP-UCONN-RF",
                              "UConn 64-cell LFP/graphite RPT data")
        _require_supported_chemistry(chemistry, {"NMC", "LCO", "NMCLCO"})
        values = _feature_vector(features, SOH_FEATURES)
        prediction = float(np.clip(self._soh.predict(values), 0.0, 105.0))
        return AIEstimate(prediction, "%", "SOH-NASA-LIION-BAG", "NASA NMC/LCO 18650")

    def predict_rul(self, features: Mapping[str, float], *, chemistry: str) -> AIEstimate:
        if _chemistry_key(chemistry) == "LFP":
            values = _feature_vector(features, LFP_RUL_FEATURES)
            if self._lfp_rul is None:
                self._lfp_rul = _PortableEnsemble(self.model_dir, "lfp_rul_ensemble.json")
            prediction = float(np.clip(self._lfp_rul.predict(values), 0.0, 10000.0))
            return AIEstimate(prediction, "cycles", "RUL-LFP-UCONN-RF",
                              "UConn 64-cell LFP/graphite RPT data")
        _require_supported_chemistry(chemistry, {"NMC", "LCO", "NMCLCO"})
        values = _feature_vector(features, RUL_FEATURES)
        prediction = float(np.clip(self._rul.predict(values), 0.0, 152.0))
        return AIEstimate(prediction, "cycles", "RUL-NASA-LIION-LSBOOST", "NASA NMC/LCO 18650")

    def predict_soh_vector(self, values: np.ndarray, *, chemistry: str) -> AIEstimate:
        _require_supported_chemistry(chemistry, {"NMC", "LCO", "NMCLCO"})
        vector = np.asarray(values, dtype=np.float64)
        if vector.shape != (len(SOH_FEATURES),) or not np.isfinite(vector).all():
            raise ValueError(f"SOH vector must contain {len(SOH_FEATURES)} finite values")
        return AIEstimate(float(np.clip(self._soh.predict(vector), 0.0, 105.0)), "%",
                          "SOH-NASA-LIION-BAG", "NASA NMC/LCO 18650")

    def predict_rul_vector(self, values: np.ndarray, *, chemistry: str) -> AIEstimate:
        _require_supported_chemistry(chemistry, {"NMC", "LCO", "NMCLCO"})
        vector = np.asarray(values, dtype=np.float64)
        if vector.shape != (len(RUL_FEATURES),) or not np.isfinite(vector).all():
            raise ValueError(f"RUL vector must contain {len(RUL_FEATURES)} finite values")
        return AIEstimate(float(np.clip(self._rul.predict(vector), 0.0, 152.0)), "cycles",
                          "RUL-NASA-LIION-LSBOOST", "NASA NMC/LCO 18650")
