"""Integration tests for local full workflow execution."""

from __future__ import annotations

from pathlib import Path

from agentic_de_pipeline.workflow.bootstrap import build_orchestrator


def test_local_full_workflow_runs_across_all_stages(test_config) -> None:
    """End-to-end run should complete Dev->QE->Stg->Prod in simulate mode."""
    orchestrator = build_orchestrator(test_config)

    summary = orchestrator.run_once()

    assert summary is not None
    assert summary.overall_status == "succeeded"
    assert [row.environment for row in summary.stage_results] == ["dev", "qe", "stg", "prod"]
    assert all(row.status == "succeeded" for row in summary.stage_results)
    assert "Databricks apply skipped for stage=qe" in summary.stage_results[1].details

    jobs_path = Path(test_config.databricks.job_yaml_folder)
    assert jobs_path.exists()
    # Default workflow applies Databricks changes in DEV only.
    assert len(list(jobs_path.glob("*_work_item_*.yaml"))) >= 1
