"""Append-only simulation lifecycle records with deterministic replay."""

import json
import hashlib
import math
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = {"timestamp_s", "event_type", "configuration", "faults", "degradation"}


def validate_record(record: dict[str, Any]) -> dict[str, Any]:
    missing = REQUIRED_FIELDS - record.keys()
    if missing:
        raise ValueError("missing lifecycle fields: " + ", ".join(sorted(missing)))
    if (
        isinstance(record["timestamp_s"], bool)
        or not isinstance(record["timestamp_s"], (int, float))
        or not math.isfinite(record["timestamp_s"])
        or record["timestamp_s"] < 0
    ):
        raise ValueError("timestamp_s must be nonnegative")
    if not isinstance(record["event_type"], str) or not record["event_type"].strip():
        raise ValueError("event_type must be nonempty")
    for key in ("configuration", "faults", "degradation"):
        if not isinstance(record[key], (dict, list)):
            raise ValueError(f"{key} must be an object or array")
    return record


class BatteryPassport:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, record: dict[str, Any]) -> None:
        clean = validate_record(record)
        previous_hash = self._last_hash()
        digest = self._record_hash(clean, previous_hash or "")
        stored = {**clean, "_integrity": {
            "algorithm": "sha256-chain-v1",
            "previous_record_sha256": previous_hash,
            "record_sha256": digest,
        }}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(stored, sort_keys=True, allow_nan=False) + "\n")

    @staticmethod
    def _record_hash(record: dict[str, Any], previous_hash: str) -> str:
        canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256((previous_hash + "|" + canonical).encode("utf-8")).hexdigest()

    def _read_entries(self) -> tuple[list[dict[str, Any]], str | None]:
        if not self.path.exists():
            return [], None
        records = []
        previous_hash = None
        with self.path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    stored = json.loads(line)
                    integrity = stored.pop("_integrity", None)
                    record = validate_record(stored)
                    if integrity is None:
                        # Preserve replay compatibility for pre-chain logs.
                        canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)
                        previous_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                    else:
                        if integrity.get("algorithm") != "sha256-chain-v1":
                            raise ValueError("unsupported integrity algorithm")
                        if integrity.get("previous_record_sha256") != previous_hash:
                            raise ValueError("broken previous-record hash")
                        expected = self._record_hash(record, previous_hash or "")
                        if integrity.get("record_sha256") != expected:
                            raise ValueError("record hash mismatch")
                        previous_hash = expected
                    records.append(record)
                except (json.JSONDecodeError, ValueError, AttributeError) as exc:
                    raise ValueError(f"invalid lifecycle record at line {line_number}: {exc}") from exc
        return records, previous_hash

    def _last_hash(self) -> str | None:
        _, last = self._read_entries()
        return last

    def replay(self) -> list[dict[str, Any]]:
        records, _ = self._read_entries()
        return records
