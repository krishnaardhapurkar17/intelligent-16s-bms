# Clean-environment reproduction record

Date: 10 November 2026

## Environment

- Python 3.13.7, 64-bit Windows
- Fresh `.venv-clean` virtual environment with
  `include-system-site-packages = false`
- Dependencies installed from `environment/requirements-core.txt`
- Optional TensorFlow dependencies were not installed

## Commands and results

```powershell
.\.venv-clean\Scripts\python.exe -m pytest tests\unit -q
.\.venv-clean\Scripts\python.exe tests\regression\run_regression.py
```

- Unit suite: 68 passed, 3 skipped. The skips are optional TensorFlow checks.
- Regression suite: 46 passed, 0 failed, 0 errors, 0 timeouts, 0 missing, and
  0 blocked in 139.517 seconds.
- Report: `results/regression/regression_report.json`

This verifies reproduction of the declared core simulation stack in an
isolated environment. It does not verify the optional TensorFlow SOC runtime,
MATLAB export regeneration, KiCad tools, or physical hardware.
