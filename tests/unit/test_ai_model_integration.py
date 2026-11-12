import json
from pathlib import Path

import numpy as np
import pytest

from software.estimation.ai_battery_estimators import (
    BatteryAIEstimators,
    LFP_RUL_FEATURES,
    LFP_SOH_FEATURES,
    RUL_FEATURES,
    SOH_FEATURES,
    UnsupportedChemistryError,
)


ROOT = Path(__file__).resolve().parents[2]
AI_DIR = ROOT / "models" / "ai"


@pytest.mark.parametrize("filename,method", [
    ("soh_ensemble.json", "predict_soh_vector"),
    ("rul_ensemble.json", "predict_rul_vector"),
])
def test_portable_matlab_export_matches_reference_predictions(filename, method):
    payload = json.loads((AI_DIR / filename).read_text(encoding="utf-8"))
    assert payload["validation_bias_spread"] < 1e-9
    assert len(payload["trees"]) == len(payload["weights"])
    estimator = BatteryAIEstimators()
    model = estimator._soh if method == "predict_soh_vector" else estimator._rul
    for vector, expected in zip(
        payload["validation_features"], payload["validation_predictions"], strict=True
    ):
        actual = model.predict(np.asarray(vector))
        assert actual == pytest.approx(expected, rel=0, abs=1e-8)


def test_soh_and_rul_accept_named_trained_features_and_return_units():
    estimator = BatteryAIEstimators()
    soh = dict(zip(SOH_FEATURES, [20, 0.08, 0.10, 24, 0.12, -0.004], strict=True))
    rul = dict(zip(RUL_FEATURES, [20, 90, 0.08, 0.10, 24, 0.12, -0.004], strict=True))
    soh_estimate = estimator.predict_soh(soh, chemistry="NMC")
    rul_estimate = estimator.predict_rul(rul, chemistry="LCO")
    assert 0 <= soh_estimate.value <= 105
    assert soh_estimate.unit == "%"
    assert 0 <= rul_estimate.value <= 152
    assert rul_estimate.unit == "cycles"
    assert soh_estimate.evidence_status == "RESEARCH_ONLY"
    message = soh_estimate.to_message(timestamp_s=123.0, cell_index=1)
    assert message.quality == "WARNING"
    assert message.unit == "%"


def test_lfp_rpt_models_are_available_as_research_only_predictions():
    estimator = BatteryAIEstimators()
    soh = dict(zip(LFP_SOH_FEATURES, [500, 0.017, 12], strict=True))
    rul = dict(zip(LFP_RUL_FEATURES, [500, 97, 2.5], strict=True))

    soh_estimate = estimator.predict_soh(soh, chemistry="LFP")
    rul_estimate = estimator.predict_rul(rul, chemistry="LFP")

    assert 0 <= soh_estimate.value <= 110
    assert soh_estimate.unit == "%"
    assert soh_estimate.training_domain == "UConn 64-cell LFP/graphite RPT data"
    assert soh_estimate.evidence_status == "RESEARCH_ONLY"
    assert 0 <= rul_estimate.value <= 10000
    assert rul_estimate.unit == "cycles"
    assert rul_estimate.evidence_status == "RESEARCH_ONLY"


def test_soc_model_rejects_lfp_without_cell_held_out_evidence():
    estimator = BatteryAIEstimators()
    with pytest.raises(UnsupportedChemistryError):
        estimator.predict_soc_window(np.zeros((30, 3)), chemistry="LFP")


def test_soc_lstm_loads_and_predicts_a_window():
    pytest.importorskip("tensorflow")
    estimator = BatteryAIEstimators()
    window = np.tile(np.asarray([3.7, -2.0, 25.0], dtype=np.float32), (30, 1))
    estimate = estimator.predict_soc_window(window, chemistry="NMC")
    assert 0 <= estimate.value <= 1
    assert estimate.model_id == "SOC-CNN-LSTM"
    estimator.reset_soc()
    for _ in range(29):
        assert estimator.update_soc(
            voltage_v=3.7, current_a=-2.0, temperature_c=25.0, chemistry="NMC"
        ) is None
    assert estimator.update_soc(
        voltage_v=3.7, current_a=-2.0, temperature_c=25.0, chemistry="NMC"
    ) is not None


def test_soc_rejects_wrong_window_shape_and_nonfinite_inputs():
    pytest.importorskip("tensorflow")
    estimator = BatteryAIEstimators()
    with pytest.raises(ValueError):
        estimator.predict_soc_window(np.zeros((29, 3)), chemistry="NMC")
    bad = np.zeros((30, 3))
    bad[0, 0] = np.nan
    with pytest.raises(ValueError):
        estimator.predict_soc_window(bad, chemistry="NMC")


def test_soc_lstm_reproduces_held_out_nmc069_five_degree_result():
    pytest.importorskip("tensorflow")
    import pandas as pd

    source_dir = ROOT / "AI models" / "battery_guardian_mk2-main" / "models_lstm"
    required = [source_dir / "seq_metadata.csv", source_dir / "sequences_X.npy",
                source_dir / "sequences_y.npy"]
    if not all(path.is_file() for path in required):
        pytest.skip("supplied SOC held-out sequence set is not present")
    metadata = pd.read_csv(required[0])
    indices = np.flatnonzero(
        (metadata["cell_id"].to_numpy() == "NMC069")
        & (metadata["temperature"].to_numpy() == 5)
    )
    assert len(indices) == 21013
    sequences = np.load(required[1], mmap_mode="r")
    targets = np.load(required[2], mmap_mode="r")
    estimator = BatteryAIEstimators()
    model = estimator._load_soc_model()
    predictions = []
    for start in range(0, len(indices), 256):
        batch = np.asarray(sequences[indices[start:start + 256]], dtype=np.float32)
        predictions.extend(np.asarray(model(batch, training=False)).reshape(-1).tolist())
    predicted = np.clip(np.asarray(predictions), 0, 1)
    actual = np.asarray(targets[indices], dtype=np.float64)
    mae_pct = float(np.mean(np.abs(predicted - actual)) * 100)
    max_error_pct = float(np.max(np.abs(predicted - actual)) * 100)
    metadata_reported = float(estimator._soc_metadata["mae_5deg"])
    assert mae_pct == pytest.approx(metadata_reported, abs=0.03)
    assert mae_pct < 3.0
    assert max_error_pct < 15.0
