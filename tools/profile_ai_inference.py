"""Measure desktop CPU latency and process memory for available AI inference paths."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time
import tracemalloc

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from software.estimation.ai_battery_estimators import BatteryAIEstimators


def working_set_mb() -> float | None:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        psapi = ctypes.WinDLL("psapi")
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        handle = kernel32.GetCurrentProcess()
        if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return counters.WorkingSetSize / (1024 * 1024)
    return None


def benchmark(name, call, repetitions=1000):
    for _ in range(10):
        call()
    samples = []
    for _ in range(repetitions):
        start = time.perf_counter_ns()
        call()
        samples.append((time.perf_counter_ns() - start) / 1e6)
    return {"name": name, "repetitions": repetitions,
            "median_ms": statistics.median(samples),
            "p95_ms": float(np.percentile(samples, 95)),
            "max_ms": max(samples)}


def main() -> int:
    tracemalloc.start()
    rss_before = working_set_mb()
    estimator = BatteryAIEstimators()
    nmc_soh = {"cycle": 100.0, "Re": 0.02, "Rct": 0.03,
               "ambient_temperature": 25.0, "capacity_fade": 0.04, "delta_Capacity": 0.01}
    nmc_rul = {"cycle": 100.0, "SOH": 0.96, "Re": 0.02, "Rct": 0.03,
               "ambient_temperature": 25.0, "capacity_fade": 0.04, "delta_Capacity": 0.01}
    lfp_soh = {"cumulative_cycles": 500.0, "pulse_resistance_ohm_mean": 0.018,
               "pulse_soc_count": 4.0}
    lfp_rul = {"cumulative_cycles": 500.0, "soh_pct": 92.0,
               "pulse_resistance_ohm_mean": 0.018, "pulse_soc_count": 4.0,
               "soh_fade_pct_per_1000_cycles": 8.0}
    results = [
        benchmark("NMC/NMC-LCO SOH portable ensemble", lambda: estimator.predict_soh(nmc_soh, chemistry="NMC")),
        benchmark("NMC/NMC-LCO RUL portable ensemble", lambda: estimator.predict_rul(nmc_rul, chemistry="NMC")),
        benchmark("LFP SOH portable forest", lambda: estimator.predict_soh(lfp_soh, chemistry="LFP")),
        benchmark("LFP RUL portable forest", lambda: estimator.predict_rul(lfp_rul, chemistry="LFP")),
    ]
    tf_available = importlib.util.find_spec("tensorflow") is not None
    soc_result = {"available": False, "reason": "TensorFlow not installed"}
    if tf_available:
        norm = json.loads((ROOT / "models/ai/soc_norm_constants.json").read_text(encoding="utf-8"))
        window = np.tile(np.array([norm["V_min"], norm["I_min"], norm["T_min"]], dtype=np.float32),
                         (int(norm["SEQ_LEN"]), 1))
        try:
            soc_result = {"available": True,
                          "benchmark": benchmark("NMC SOC CNN-LSTM", lambda: estimator.predict_soc_window(window, chemistry="NMC"), 100)}
        except Exception as exc:
            soc_result = {"available": False, "reason": f"inference failed: {type(exc).__name__}: {exc}"}
    current, peak = tracemalloc.get_traced_memory()
    report = {
        "environment": {"python": sys.version, "platform": platform.platform(),
                        "processor": platform.processor(), "logical_cpu_count": os.cpu_count()},
        "memory": {"working_set_before_mb": rss_before,
                   "working_set_after_mb": working_set_mb(),
                   "python_traced_current_mb": current / (1024 * 1024),
                   "python_traced_peak_mb": peak / (1024 * 1024)},
        "portable_model_benchmarks": results,
        "soc_cnn_lstm": soc_result,
        "limitations": [
            "Desktop results do not estimate Raspberry Pi performance.",
            "Latency covers warmed single-sample calls in one process, not concurrent load or end-to-end telemetry.",
            "Memory is whole-process working set plus Python traced allocations; TensorFlow native allocations may not be fully represented by tracemalloc.",
            "Feature values are representative schema-valid inputs; benchmark metrics do not imply model accuracy.",
        ],
    }
    out = ROOT / "results/metrics/ai_inference_profile.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print("Report:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
