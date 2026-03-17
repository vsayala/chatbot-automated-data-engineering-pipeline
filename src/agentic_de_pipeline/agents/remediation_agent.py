"""Failure remediation agent for pipeline/test errors."""

from __future__ import annotations

from agentic_de_pipeline.logging_utils import get_module_logger
from agentic_de_pipeline.models import RequirementPlan
from agentic_de_pipeline.services.prompt_engine import PromptEngine


class FailureRemediationAgent:
    """Builds remediation suggestions from pipeline failure context."""

    def __init__(self, log_dir: str, prompt_engine: PromptEngine) -> None:
        self.prompt_engine = prompt_engine
        self.logger = get_module_logger(
            module_name="agentic_de_pipeline.remediation_agent",
            log_dir=log_dir,
            file_name="remediation_agent.log",
        )

    def suggest_fix(self, environment: str, plan: RequirementPlan, failure_context: str, attempt: int) -> str:
        """Generate actionable remediation suggestion text."""
        prompt = self.prompt_engine.render(
            "failure_remediation",
            {
                "environment": environment,
                "attempt": attempt,
                "target_table": f"{plan.target_catalog}.{plan.target_schema}.{plan.target_table}",
                "repo": plan.target_repo,
                "ingestion_mode": plan.ingestion_mode,
                "failure_context": failure_context,
                "fallback": (
                    f"Investigate {environment} pipeline failure for {plan.target_table}. "
                    "Focus on schema mismatch, missing source credentials, and DQ rule failures."
                ),
            },
        )
        suggestion = self.prompt_engine.generate_text(prompt)
        self.logger.info(
            "remediation_suggestion_generated environment=%s work_item_id=%s attempt=%s",
            environment,
            plan.work_item_id,
            attempt,
        )
        return suggestion
