"""Unit tests for requirement interpretation logic."""

from __future__ import annotations

from datetime import UTC, datetime

from agentic_de_pipeline.agents.requirement_agent import RequirementAgent
from agentic_de_pipeline.models import LearningRecord, WorkItem, WorkItemType
from agentic_de_pipeline.state_store import LearningStore


def test_requirement_agent_extracts_core_fields(tmp_path) -> None:
    """Agent should infer sources, mode, and target table details."""
    learning_store = LearningStore(str(tmp_path / "learning.json"))
    learning_store.add_record(
        LearningRecord(
            work_item_id=1,
            title="Previous flat-file job",
            status="succeeded",
            target_table="legacy_table",
            source_types=["flat_file"],
            created_at=datetime.now(UTC),
        )
    )
    agent = RequirementAgent(log_dir=str(tmp_path / "logs"), learning_store=learning_store)

    work_item = WorkItem(
        id=25,
        title="Create main.bronze.customer_dim from JDBC and flat file with overwrite",
        description="Connect EDW using JDBC and backup flat file volume.",
        item_type=WorkItemType.USER_STORY,
        acceptance_criteria="Overwrite mode with DQ checks.",
    )

    plan = agent.build_plan(work_item)

    assert plan.target_catalog == "main"
    assert plan.target_schema == "bronze"
    assert plan.target_table == "customer_dim"
    assert plan.ingestion_mode == "overwrite"
    assert set(plan.source_types) == {"jdbc", "flat_file"}
    assert "create_unity_catalog_table" in plan.notebook_tasks
    assert any("overwrite" in note.lower() for note in plan.risk_notes)
