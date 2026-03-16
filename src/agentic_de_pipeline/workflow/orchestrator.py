"""Main orchestration engine for the agentic CI/CD lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime

from agentic_de_pipeline.adapters.azure_devops import AzureDevOpsClient
from agentic_de_pipeline.adapters.azure_pipelines import AzurePipelinesClient
from agentic_de_pipeline.adapters.databricks import DatabricksWorkspaceClient
from agentic_de_pipeline.agents.implementation_agent import ImplementationAgent
from agentic_de_pipeline.agents.promotion_agent import PromotionAgent
from agentic_de_pipeline.agents.qa_agent import QAAgent
from agentic_de_pipeline.agents.requirement_agent import RequirementAgent
from agentic_de_pipeline.approvals.human_loop import HumanApprovalService
from agentic_de_pipeline.logging_utils import get_module_logger
from agentic_de_pipeline.models import ApprovalStatus, LearningRecord, StageResult, WorkflowRunSummary
from agentic_de_pipeline.services.developer_workflow import DeveloperWorkflowService
from agentic_de_pipeline.state_store import LearningStore
from agentic_de_pipeline.utils.timing import timed_operation


class AgenticOrchestrator:
    """Coordinates requirement intake, implementation, testing, approvals, and promotion."""

    def __init__(
        self,
        devops_client: AzureDevOpsClient,
        pipelines_client: AzurePipelinesClient,
        databricks_client: DatabricksWorkspaceClient,
        requirement_agent: RequirementAgent,
        implementation_agent: ImplementationAgent,
        qa_agent: QAAgent,
        promotion_agent: PromotionAgent,
        approval_service: HumanApprovalService,
        learning_store: LearningStore,
        developer_workflow: DeveloperWorkflowService,
        max_work_items_per_run: int,
        stage_sequence: list[str],
        databricks_apply_in_stages: list[str],
        hil_approval_stages: list[str],
        log_dir: str,
    ) -> None:
        self.devops_client = devops_client
        self.pipelines_client = pipelines_client
        self.databricks_client = databricks_client
        self.requirement_agent = requirement_agent
        self.implementation_agent = implementation_agent
        self.qa_agent = qa_agent
        self.promotion_agent = promotion_agent
        self.approval_service = approval_service
        self.learning_store = learning_store
        self.developer_workflow = developer_workflow
        self.max_work_items_per_run = max_work_items_per_run
        self.stage_sequence = stage_sequence
        self.databricks_apply_in_stages = set(databricks_apply_in_stages)
        self.hil_approval_stages = set(hil_approval_stages)
        self.logger = get_module_logger(
            module_name="agentic_de_pipeline.orchestrator",
            log_dir=log_dir,
            file_name="orchestrator.log",
        )

    def run_once(self) -> WorkflowRunSummary | None:
        """Process one highest-priority work item from intake to promotion chain."""
        with timed_operation(self.logger, "orchestrator_run_once"):
            items = self.devops_client.fetch_open_work_items(limit=self.max_work_items_per_run)
            if not items:
                self.logger.info("orchestrator_no_work_items")
                return None

            work_item = items[0]
            plan = self.requirement_agent.build_plan(work_item)
            repo_status, repo_details = self.developer_workflow.execute(work_item=work_item, plan=plan)

            stage_results: list[StageResult] = []
            overall_status = "succeeded"
            if repo_status == "failed":
                overall_status = "failed"
                self.logger.error(
                    "orchestrator_repo_workflow_failed work_item_id=%s details=%s",
                    work_item.id,
                    repo_details,
                )

            for environment in self.stage_sequence:
                if overall_status == "failed":
                    break

                stage_start = datetime.now(UTC)
                notes = self.implementation_agent.build_execution_notes(plan, environment)
                approval_details = "Approval not required."

                if environment in self.hil_approval_stages:
                    approval = self.approval_service.request_approval(stage=environment, summary=notes)
                    approval_details = (
                        f"approval_status={approval.status.value}, approver={approval.approver}, comment={approval.comment}"
                    )
                    if approval.status != ApprovalStatus.APPROVED:
                        stage_results.append(
                            StageResult(
                                environment=environment,
                                status="failed",
                                details=f"Promotion denied at {environment}. {approval_details}",
                                started_at=stage_start,
                                finished_at=datetime.now(UTC),
                            )
                        )
                        overall_status = "failed"
                        break

                if environment in self.databricks_apply_in_stages:
                    db_result = self.databricks_client.apply_plan(environment=environment, plan=plan)
                    databricks_details = db_result.details
                else:
                    databricks_details = f"Databricks apply skipped for stage={environment} by workflow config."
                pipeline_result = self.pipelines_client.run_cicd(environment=environment, plan=plan)
                qa_passed, qa_details = self.qa_agent.validate_stage(environment=environment, plan=plan)
                can_promote, promotion_reason = self.promotion_agent.can_promote(
                    environment=environment,
                    pipeline_status=pipeline_result.status,
                    qa_passed=qa_passed,
                )

                stage_status = "succeeded" if can_promote else "failed"
                details = " | ".join(
                    [
                        notes,
                        approval_details,
                        databricks_details,
                        f"pipeline_run_id={pipeline_result.run_id}",
                        qa_details,
                        promotion_reason,
                    ]
                )
                stage_results.append(
                    StageResult(
                        environment=environment,
                        status=stage_status,
                        details=details,
                        started_at=stage_start,
                        finished_at=datetime.now(UTC),
                    )
                )

                if not can_promote:
                    overall_status = "failed"
                    break

            self.learning_store.add_record(
                LearningRecord(
                    work_item_id=work_item.id,
                    title=work_item.title,
                    status=overall_status,
                    target_table=plan.target_table,
                    source_types=plan.source_types,
                )
            )

            summary = WorkflowRunSummary(
                work_item_id=work_item.id,
                work_item_title=work_item.title,
                overall_status=overall_status,
                repo_workflow_status=repo_status,
                repo_workflow_details=repo_details,
                stage_results=stage_results,
            )
            self.logger.info(
                "orchestrator_completed work_item_id=%s status=%s stages=%s repo_status=%s",
                summary.work_item_id,
                summary.overall_status,
                len(summary.stage_results),
                summary.repo_workflow_status,
            )
            return summary
