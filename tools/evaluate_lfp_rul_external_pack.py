"""Score the UConn-trained LFP RUL model on the separate GMP 40 Ah pack."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from software.estimation.ai_battery_estimators import BatteryAIEstimators, LFP_RUL_FEATURES  # noqa: E402

DATASET = next((ROOT / "datasets").glob("Industrial*/**/GMP_LFP_40Ah_3000Cycle.csv"))
OUT = ROOT / "results/metrics/lfp_rul_external_pack_validation.json"


def metrics(actual: np.ndarray, predicted: np.ndarray) -> dict:
    error = predicted - actual
    return {"rows": int(len(error)), "mae_cycles": float(np.mean(np.abs(error))),
            "rmse_cycles": float(np.sqrt(np.mean(error ** 2))),
            "max_absolute_error_cycles": float(np.max(np.abs(error)))}


def main() -> int:
    data = pd.read_csv(DATASET)
    required = {"PackID", "CycleNumber", "SOH(%)", "RUL(cycles)"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"External pack dataset is missing columns: {sorted(missing)}")
    pack_ids = data["PackID"].dropna().unique().tolist()
    data = data.sort_values(["PackID", "CycleNumber"]).reset_index(drop=True)
    if len(pack_ids) != 1:
        raise ValueError(f"Expected the documented single pack, found {len(pack_ids)}")

    # Past-only four-cycle least-squares slope, scaled to SOH percentage points
    # per 1,000 cycles. No row after the scored observation is used.
    fade = np.zeros(len(data), dtype=float)
    cycle = data["CycleNumber"].to_numpy(dtype=float)
    soh = data["SOH(%)"].to_numpy(dtype=float)
    for index in range(len(data)):
        start = max(0, index - 3)
        x = cycle[start:index + 1]
        y = soh[start:index + 1]
        if len(x) < 2:
            continue
        centered = x - x.mean()
        denominator = float(centered @ centered)
        slope = float(centered @ (y - y.mean()) / denominator) if denominator else 0.0
        fade[index] = max(0.0, -slope * 1000.0)

    estimator = BatteryAIEstimators()
    predictions = []
    for (_, row), rate in zip(data.iterrows(), fade, strict=True):
        vector = {"cumulative_cycles": float(row["CycleNumber"]),
                  "soh_pct": float(row["SOH(%)"]),
                  "soh_fade_pct_per_1000_cycles": float(rate)}
        estimate = estimator.predict_rul(vector, chemistry="LFP")
        predictions.append(float(estimate.value))
    actual = data["RUL(cycles)"].to_numpy(dtype=float)
    predicted = np.asarray(predictions, dtype=float)

    # Partition by cycle index only for descriptive error summaries; the model
    # has no access to these labels when predicting.
    bins = np.array_split(np.arange(len(data)), 4)
    quartiles = []
    for indices in bins:
        quartiles.append({"cycle_start": int(cycle[indices[0]]),
                          "cycle_end": int(cycle[indices[-1]]),
                          **metrics(actual[indices], predicted[indices])})

    report = {
        "dataset": "GMP LFP 40 Ah 3000-cycle dataset",
        "source_path": str(DATASET.relative_to(ROOT)),
        "pack_count": len(pack_ids), "pack_ids": pack_ids,
        "rows": len(data), "feature_contract": list(LFP_RUL_FEATURES),
        "target_definition": "RUL(cycles) through the final observed dataset cycle; the supplied target equals 3000 minus CycleNumber.",
        "target_formula_exact_fraction": float(np.mean(np.isclose(actual, 3000.0 - cycle))),
        "model_metrics": metrics(actual, predicted),
        "cycle_quartile_metrics": quartiles,
        "limitations": [
            "This is a separate data source and was not used to fit this model, but it contains only one pack and cannot establish between-pack generalization.",
            "The supplied RUL labels are deterministically defined by the dataset end cycle, not independently observed per-pack end of life.",
            "Feature extraction uses a past-only four-cycle SOH slope; pulse resistance is omitted under the selected three-feature contract.",
            "Cell format and aging protocol differ from the 64-cell UConn RPT training domain; treat results as a distribution-shift stress test.",
            "Model output remains research-only and must not control battery protection.",
        ],
        "status": "RESEARCH_ONLY_EXTERNAL_SINGLE_PACK_STRESS_TEST",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print("Report:", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
