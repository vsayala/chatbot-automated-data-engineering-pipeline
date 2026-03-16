"""Unit tests for requirement interpretation logic."""

from __future__ import annotations

from datetime import UTC, datetime

from agentic_de_pipeline.agents.requirement_agent import RequirementAgent
from agentic_de_pipeline.models import LearningRecord, WorkItem, WorkItemType
from agentic_de_pipeline.services.mcp_router import MCPRouter
from agentic_de_pipeline.services.prompt_engine import PromptEngine
from agentic_de_pipeline.state_store import LearningStore


def test_requirement_agent_extracts_core_fields(tmp_path) -> None:
    """Agent should infer sources, mode, target table, repo, and branch details."""
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

    class PromptConfigStub:
        enabled = True
        templates_path = "config/prompts.yaml"
        llm_enabled = False
        llm_endpoint_url = None
        llm_model = ""
        llm_api_key_env = ""
        llm_api_key = None

    class MCPConfigStub:
        enabled = False
        servers = {}
        server_tokens = {}

    agent = RequirementAgent(
        log_dir=str(tmp_path / "logs"),
        learning_store=learning_store,
        prompt_engine=PromptEngine(PromptConfigStub(), str(tmp_path / "logs")),
        mcp_router=MCPRouter(MCPConfigStub(), str(tmp_path / "logs")),
        default_repo_name="default-repo",
        branch_prefix="feature/pbi-",
    )

    work_item = WorkItem(
        id=25,
        title="Create main.bronze.customer_dim from JDBC and flat file with overwrite",
        description="Connect EDW using JDBC and backup flat file volume.",
        item_type=WorkItemType.USER_STORY,
        acceptance_criteria="Overwrite mode with DQ checks.",
        repo_name="analytics-repo",
    )

    plan = agent.build_plan(work_item)

    assert plan.target_catalog == "main"
    assert plan.target_schema == "bronze"
    assert plan.target_table == "customer_dim"
    assert plan.ingestion_mode == "overwrite"
    assert set(plan.source_types) == {"jdbc", "flat_file"}
    assert plan.target_repo == "analytics-repo"
    assert plan.branch_name.startswith("feature/pbi-25-")
    assert "create_unity_catalog_table" in plan.notebook_tasks
    assert any("overwrite" in note.lower() for note in plan.risk_notes)
