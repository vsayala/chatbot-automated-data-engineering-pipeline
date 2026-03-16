"""Factory functions to wire orchestrator dependencies."""

from __future__ import annotations

from agentic_de_pipeline.adapters.azure_devops import AzureDevOpsClient
from agentic_de_pipeline.adapters.azure_pipelines import AzurePipelinesClient
from agentic_de_pipeline.adapters.databricks import DatabricksWorkspaceClient
from agentic_de_pipeline.agents.implementation_agent import ImplementationAgent
from agentic_de_pipeline.agents.promotion_agent import PromotionAgent
from agentic_de_pipeline.agents.qa_agent import QAAgent
from agentic_de_pipeline.agents.requirement_agent import RequirementAgent
from agentic_de_pipeline.approvals.human_loop import HumanApprovalService
from agentic_de_pipeline.config import AppConfig
from agentic_de_pipeline.logging_utils import configure_logging
from agentic_de_pipeline.state_store import LearningStore
from agentic_de_pipeline.workflow.orchestrator import AgenticOrchestrator


def build_orchestrator(config: AppConfig) -> AgenticOrchestrator:
    """Create a fully wired orchestrator instance from app config."""
    configure_logging(config.logging.log_dir, config.logging.log_level)

    learning_store = LearningStore(config.learning_store_path)
    devops_client = AzureDevOpsClient(config)
    pipelines_client = AzurePipelinesClient(config)
    databricks_client = DatabricksWorkspaceClient(config)
    requirement_agent = RequirementAgent(config.logging.log_dir, learning_store)
    implementation_agent = ImplementationAgent(config.logging.log_dir)
    qa_agent = QAAgent(config.logging.log_dir)
    promotion_agent = PromotionAgent(config.logging.log_dir)
    approval_service = HumanApprovalService(config.approvals, config.logging.log_dir)

    return AgenticOrchestrator(
        devops_client=devops_client,
        pipelines_client=pipelines_client,
        databricks_client=databricks_client,
        requirement_agent=requirement_agent,
        implementation_agent=implementation_agent,
        qa_agent=qa_agent,
        promotion_agent=promotion_agent,
        approval_service=approval_service,
        learning_store=learning_store,
        log_dir=config.logging.log_dir,
    )
