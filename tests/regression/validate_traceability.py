"""Check requirement evidence paths and verification scenario references."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RTM = ROOT / "docs" / "requirements-traceability-matrix.md"
OUTPUT = ROOT / "results" / "regression" / "traceability_validation.json"


def main() -> int:
    text = RTM.read_text(encoding="utf-8")
    requirement_rows = []
    scenario_rows = []
    section = ""
    for line in text.splitlines():
        if line.startswith("## 4."):
            section = "requirements"
        elif line.startswith("## 5."):
            section = "nonfunctional"
        elif line.startswith("## 6."):
            section = "scenarios"
        elif line.startswith("## "):
            section = ""
        if not line.startswith("| SYS-") and not (section == "scenarios" and line.startswith("| SIM-")):
            continue
        cells = [part.strip() for part in line.strip().strip("|").split("|")]
        if section in ("requirements", "nonfunctional") and cells[0].startswith("SYS-"):
            evidence = cells[4]
            paths = re.findall(r"(?:[\w.-]+/)+(?:[\w.-]+(?:\.[\w.-]+)?)?", evidence)
            missing = [path for path in paths if not (ROOT / Path(path)).exists()]
            requirement_rows.append({
                "requirement_id": cells[0],
                "verification_ids": cells[3],
                "evidence_paths": paths,
                "missing_paths": missing,
                "status": cells[5],
                "passed": not missing and bool(paths),
            })
        elif section == "scenarios" and cells[0].startswith("SIM-"):
            scenario_rows.append({"verification_id": cells[0], "requirements": cells[2], "status": cells[4]})

    scenario_ids = {row["verification_id"] for row in scenario_rows}
    for row in requirement_rows:
        ids = re.findall(r"SIM-\d+", row["verification_ids"])
        row["unmapped_verification_ids"] = [item for item in ids if item not in scenario_ids]
        row["passed"] = row["passed"] and not row["unmapped_verification_ids"]

    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "matrix": str(RTM.relative_to(ROOT)),
        "requirements_checked": len(requirement_rows),
        "requirements_with_all_evidence_present": sum(row["passed"] for row in requirement_rows),
        "scenario_rows_checked": len(scenario_rows),
        "requirements": requirement_rows,
        "scenarios": scenario_rows,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    missing = [row for row in requirement_rows if not row["passed"]]
    print(f"Traceability evidence rows: {len(requirement_rows)}")
    print(f"Rows with evidence present and mapped: {len(requirement_rows) - len(missing)}")
    for row in missing:
        print(row["requirement_id"], "missing:", row["missing_paths"], "unmapped:", row["unmapped_verification_ids"])
    print("Report:", OUTPUT)
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
