"""Repeat one seeded noisy simulation and compare its machine-readable outputs."""

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "models" / "pack-model" / "lfp_16s_robustness_test.py"
METRICS = ROOT / "results" / "metrics"
OUTPUTS = [
    METRICS / "lfp_16s_robustness_results.csv",
    METRICS / "lfp_16s_robustness_summary.json",
]


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_once():
    process = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if process.returncode:
        raise RuntimeError(
            f"robustness simulation failed ({process.returncode}):\n{process.stderr}\n{process.stdout}"
        )
    missing = [str(path.relative_to(ROOT)) for path in OUTPUTS if not path.exists()]
    if missing:
        raise RuntimeError("simulation did not produce: " + ", ".join(missing))
    return {str(path.relative_to(ROOT)): sha256(path) for path in OUTPUTS}


def main():
    first = run_once()
    second = run_once()
    summary = json.loads(OUTPUTS[1].read_text(encoding="utf-8"))
    report = {
        "verification_id": "SIM-012",
        "scenario": "16S LFP robustness and disturbance testing",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version,
        "numpy_version": np.__version__,
        "random_seed": summary["random_seed"],
        "model_version_sha256": sha256(SCRIPT),
        "identical_outputs": first == second,
        "output_hashes": second,
    }
    report_path = ROOT / "results" / "regression" / "reproducibility_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("SIM-012 identical seeded output hashes:", "PASS" if first == second else "FAIL")
    print("Report:", report_path)
    if first != second:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
