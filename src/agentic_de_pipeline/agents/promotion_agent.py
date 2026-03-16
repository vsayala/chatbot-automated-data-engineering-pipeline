"""Promotion decision agent for environment progression."""

from __future__ import annotations

from agentic_de_pipeline.logging_utils import get_module_logger


class PromotionAgent:
    """Evaluates whether workflow can move to next environment."""

    def __init__(self, log_dir: str) -> None:
        self.logger = get_module_logger(
            module_name="agentic_de_pipeline.promotion_agent",
            log_dir=log_dir,
            file_name="promotion_agent.log",
        )

    def can_promote(self, environment: str, pipeline_status: str, qa_passed: bool) -> tuple[bool, str]:
        """Return promotion decision and reason."""
        status_ok = pipeline_status.lower() in {"succeeded", "success", "completed"}
        can_move = status_ok and qa_passed
        reason = (
            f"Promotion allowed from {environment}."
            if can_move
            else f"Promotion blocked at {environment}: pipeline_status={pipeline_status}, qa_passed={qa_passed}."
        )
        self.logger.info(
            "promotion_evaluated environment=%s allowed=%s pipeline_status=%s qa_passed=%s",
            environment,
            can_move,
            pipeline_status,
            qa_passed,
        )
        return can_move, reason
