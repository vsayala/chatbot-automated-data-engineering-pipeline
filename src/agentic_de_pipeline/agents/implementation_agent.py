"""Implementation planning/execution agent."""

from __future__ import annotations

from agentic_de_pipeline.logging_utils import get_module_logger
from agentic_de_pipeline.models import RequirementPlan


class ImplementationAgent:
    """Builds code/deployment action checklist per environment."""

    def __init__(self, log_dir: str) -> None:
        self.logger = get_module_logger(
            module_name="agentic_de_pipeline.implementation_agent",
            log_dir=log_dir,
            file_name="implementation_agent.log",
        )

    def build_execution_notes(self, plan: RequirementPlan, environment: str) -> str:
        """Return concise execution notes used by orchestrator and approvals."""
        note = (
            f"Prepare {environment} deployment for {plan.target_catalog}.{plan.target_schema}.{plan.target_table} "
            f"using mode={plan.ingestion_mode}, sources={','.join(plan.source_types)}, "
            f"repo={plan.target_repo}, branch={plan.branch_name}"
        )
        self.logger.info(
            "implementation_notes_built work_item_id=%s environment=%s",
            plan.work_item_id,
            environment,
        )
        return note
