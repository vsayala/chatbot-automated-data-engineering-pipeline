"""Unit tests for idempotent workflow behavior."""

from __future__ import annotations

from agentic_de_pipeline.workflow.bootstrap import build_orchestrator


def test_orchestrator_skips_duplicate_successful_work_item(test_config) -> None:
    """Second run of identical work item should be skipped by idempotency store."""
    orchestrator = build_orchestrator(test_config)

    first = orchestrator.run_once()
    second = orchestrator.run_once()

    assert first is not None
    assert first.overall_status == "succeeded"
    assert second is not None
    assert second.overall_status == "skipped"
    assert second.repo_workflow_status == "skipped"
