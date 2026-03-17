"""Unit tests for pipeline failure remediation loop behavior."""

from __future__ import annotations

from datetime import UTC, datetime

from agentic_de_pipeline.agents.implementation_agent import ImplementationAgent
from agentic_de_pipeline.agents.promotion_agent import PromotionAgent
from agentic_de_pipeline.agents.qa_agent import QAAgent
from agentic_de_pipeline.models import ApprovalRequest, ApprovalStatus, PipelineRunResult, RequirementPlan, StageResult, WorkItem, WorkItemType
from agentic_de_pipeline.state_store import IdempotencyStore, LearningStore
from agentic_de_pipeline.workflow.orchestrator import AgenticOrchestrator


class DevopsStub:
    """Provide one active work item."""

    @staticmethod
    def fetch_open_work_items(limit: int = 1):  # noqa: ANN001
        return [
            WorkItem(
                id=500,
                title="Create main.bronze.test_table",
                description="Test item",
                item_type=WorkItemType.USER_STORY,
                acceptance_criteria="must pass",
                priority=1,
                repo_name="test-repo",
            )
        ]


class PipelinesStub:
    """Fail once then succeed to trigger remediation."""

    def __init__(self) -> None:
        self.calls = 0

    def run_cicd(self, environment: str, plan: RequirementPlan) -> PipelineRunResult:
        self.calls += 1
        status = "failed" if self.calls == 1 else "succeeded"
        now = datetime.now(UTC)
        return PipelineRunResult(
            run_id=f"run-{self.calls}",
            pipeline_name="stub-pipeline",
            environment=environment,
            status=status,
            started_at=now,
            finished_at=now,
            dashboard_url="http://stub",
            logs_url="http://stub/logs",
        )

    @staticmethod
    def get_failure_context(run_result: PipelineRunResult, max_chars: int = 6000) -> str:  # noqa: ARG004
        return "Schema mismatch error in ingestion notebook"


class DatabricksStub:
    """Return successful Databricks apply result."""

    @staticmethod
    def apply_plan(environment: str, plan: RequirementPlan) -> StageResult:
        now = datetime.now(UTC)
        return StageResult(
            environment=environment,
            status="succeeded",
            details="databricks apply ok",
            started_at=now,
            finished_at=now,
        )


class RequirementStub:
    """Return deterministic non-clarification plan."""

    @staticmethod
    def build_plan(work_item: WorkItem) -> RequirementPlan:
        return RequirementPlan(
            work_item_id=work_item.id,
            summary="test plan",
            source_types=["jdbc"],
            ingestion_mode="append",
            target_layer="bronze",
            target_catalog="main",
            target_schema="bronze",
            target_table="test_table",
            target_repo="test-repo",
            branch_name="feature/pbi-500-test",
            notebook_tasks=["task1"],
            needs_clarification=False,
        )


class ApprovalStub:
    """Approve all approval requests."""

    @staticmethod
    def request_approval(stage: str, summary: str) -> ApprovalRequest:  # noqa: ARG004
        now = datetime.now(UTC)
        return ApprovalRequest(
            stage=stage,
            summary=summary,
            status=ApprovalStatus.APPROVED,
            approver="approver",
            comment="ok",
            request_id=f"apr-{stage}",
            created_at=now,
            updated_at=now,
        )


class DeveloperWorkflowStub:
    """Simulate successful dev workflow and remediation actions."""

    @staticmethod
    def execute(work_item, plan):  # noqa: ANN001
        return "succeeded", "initial workflow ok"

    @staticmethod
    def apply_remediation(work_item, plan, environment, failure_context, suggestion, attempt):  # noqa: ANN001
        return "succeeded", f"applied remediation attempt={attempt}"


class PreflightStub:
    """Skip preflight external checks."""

    @staticmethod
    def validate_or_raise():
        return {"status": "ok"}


class RemediationStub:
    """Provide deterministic remediation suggestion."""

    @staticmethod
    def suggest_fix(environment: str, plan: RequirementPlan, failure_context: str, attempt: int) -> str:  # noqa: ARG004
        return f"Fix ingestion notebook for {environment}, attempt={attempt}"


def test_orchestrator_recovers_with_remediation_loop(tmp_path) -> None:
    """Orchestrator should rerun stage after remediation and recover."""
    learning_store = LearningStore(str(tmp_path / "learning.json"))
    idempotency_store = IdempotencyStore(str(tmp_path / "idempotency.json"))

    orchestrator = AgenticOrchestrator(
        devops_client=DevopsStub(),
        pipelines_client=PipelinesStub(),
        databricks_client=DatabricksStub(),
        requirement_agent=RequirementStub(),
        implementation_agent=ImplementationAgent(str(tmp_path / "logs")),
        qa_agent=QAAgent(str(tmp_path / "logs")),
        promotion_agent=PromotionAgent(str(tmp_path / "logs")),
        approval_service=ApprovalStub(),
        learning_store=learning_store,
        idempotency_store=idempotency_store,
        developer_workflow=DeveloperWorkflowStub(),
        preflight_validator=PreflightStub(),
        require_preflight_before_run=False,
        enable_idempotency=True,
        fail_fast=True,
        remediation_agent=RemediationStub(),
        enable_failure_remediation=True,
        max_failure_remediation_attempts=1,
        require_hil_approval_for_remediation=False,
        require_hil_approval_for_repo_actions=False,
        max_work_items_per_run=1,
        stage_sequence=["dev"],
        databricks_apply_in_stages=["dev"],
        hil_approval_stages=[],
        log_dir=str(tmp_path / "logs"),
    )

    summary = orchestrator.run_once()

    assert summary is not None
    assert summary.overall_status == "succeeded"
    assert len(summary.stage_results) == 1
    assert "remediation=attempt=1" in summary.stage_results[0].details
