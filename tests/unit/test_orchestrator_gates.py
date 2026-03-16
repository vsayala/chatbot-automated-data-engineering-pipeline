"""Unit tests for human-approval gating behavior."""

from __future__ import annotations

from datetime import UTC, datetime

from agentic_de_pipeline.adapters.azure_devops import AzureDevOpsClient
from agentic_de_pipeline.adapters.azure_pipelines import AzurePipelinesClient
from agentic_de_pipeline.adapters.databricks import DatabricksWorkspaceClient
from agentic_de_pipeline.agents.implementation_agent import ImplementationAgent
from agentic_de_pipeline.agents.promotion_agent import PromotionAgent
from agentic_de_pipeline.agents.qa_agent import QAAgent
from agentic_de_pipeline.agents.requirement_agent import RequirementAgent
from agentic_de_pipeline.models import ApprovalRequest, ApprovalStatus
from agentic_de_pipeline.state_store import LearningStore
from agentic_de_pipeline.workflow.orchestrator import AgenticOrchestrator


class RejectingApprovalService:
    """Reject QE stage to verify orchestrator stop behavior."""

    def request_approval(self, stage: str, summary: str) -> ApprovalRequest:
        if stage == "qe":
            return ApprovalRequest(
                stage=stage,
                summary=summary,
                status=ApprovalStatus.REJECTED,
                approver="qe-tester",
                comment="Blocked due to failed exploratory test",
                request_id="apr-test-reject",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        return ApprovalRequest(
            stage=stage,
            summary=summary,
            status=ApprovalStatus.APPROVED,
            approver="approver",
            comment="ok",
            request_id="apr-test-ok",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )


def test_orchestrator_stops_on_qe_rejection(test_config) -> None:
    """Workflow must stop if a manual approval is rejected."""
    learning_store = LearningStore(test_config.learning_store_path)
    orchestrator = AgenticOrchestrator(
        devops_client=AzureDevOpsClient(test_config),
        pipelines_client=AzurePipelinesClient(test_config),
        databricks_client=DatabricksWorkspaceClient(test_config),
        requirement_agent=RequirementAgent(test_config.logging.log_dir, learning_store),
        implementation_agent=ImplementationAgent(test_config.logging.log_dir),
        qa_agent=QAAgent(test_config.logging.log_dir),
        promotion_agent=PromotionAgent(test_config.logging.log_dir),
        approval_service=RejectingApprovalService(),
        learning_store=learning_store,
        log_dir=test_config.logging.log_dir,
    )

    summary = orchestrator.run_once()

    assert summary is not None
    assert summary.overall_status == "failed"
    assert summary.stage_results[0].environment == "dev"
    assert summary.stage_results[0].status == "succeeded"
    assert summary.stage_results[1].environment == "qe"
    assert summary.stage_results[1].status == "failed"
