"""Persistent state store utilities for approvals and learning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentic_de_pipeline.models import LearningRecord


class JsonStateStore:
    """Simple JSON file state store with local-first behavior."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("{}", encoding="utf-8")

    def read(self) -> dict[str, Any]:
        """Read state from disk."""
        content = self.path.read_text(encoding="utf-8").strip()
        if not content:
            return {}
        return json.loads(content)

    def write(self, data: dict[str, Any]) -> None:
        """Write state atomically to disk."""
        temp_path = self.path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temp_path.replace(self.path)


class LearningStore:
    """Store workflow outcomes to improve future execution planning."""

    def __init__(self, path: str) -> None:
        self.state_store = JsonStateStore(path)
        initial = self.state_store.read()
        if "records" not in initial:
            initial["records"] = []
            self.state_store.write(initial)

    def add_record(self, record: LearningRecord) -> None:
        """Append one learning record."""
        data = self.state_store.read()
        records = data.setdefault("records", [])
        records.append(
            {
                "work_item_id": record.work_item_id,
                "title": record.title,
                "status": record.status,
                "target_table": record.target_table,
                "source_types": record.source_types,
                "created_at": record.created_at.isoformat(),
            }
        )
        data["records"] = records[-500:]
        self.state_store.write(data)

    def suggest_source_priority(self) -> list[str]:
        """Return source types ranked by historical frequency."""
        data = self.state_store.read()
        scores: dict[str, int] = {}
        for row in data.get("records", []):
            for source_type in row.get("source_types", []):
                scores[source_type] = scores.get(source_type, 0) + 1
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        return [name for name, _ in ranked]
