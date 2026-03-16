"""Regression tests for learning-memory behavior."""

from __future__ import annotations

from agentic_de_pipeline.state_store import LearningStore
from agentic_de_pipeline.workflow.bootstrap import build_orchestrator


def test_learning_store_is_updated_after_workflow(test_config) -> None:
    """Workflow run should persist learning records for future planning."""
    orchestrator = build_orchestrator(test_config)
    summary = orchestrator.run_once()

    assert summary is not None

    store = LearningStore(test_config.learning_store_path)
    data = store.state_store.read()
    records = data.get("records", [])

    assert len(records) >= 1
    latest = records[-1]
    assert latest["work_item_id"] == summary.work_item_id
    assert latest["status"] in {"succeeded", "failed"}

    priority = store.suggest_source_priority()
    assert isinstance(priority, list)
