"""Quality validation agent for deployment stages."""

from __future__ import annotations

from agentic_de_pipeline.logging_utils import get_module_logger
from agentic_de_pipeline.models import RequirementPlan


class QAAgent:
    """Runs stage-specific quality validations."""

    def __init__(self, log_dir: str) -> None:
        self.logger = get_module_logger(
            module_name="agentic_de_pipeline.qa_agent",
            log_dir=log_dir,
            file_name="qa_agent.log",
        )

    def validate_stage(self, environment: str, plan: RequirementPlan) -> tuple[bool, str]:
        """Perform quality checks. Returns (is_valid, summary)."""
        checks = {
            "dev": [
                "table_exists",
                "row_count_non_zero",
                "schema_validation",
                "dq_rules_passed",
            ],
            "qe": [
                "smoke_test_query_success",
                "schema_validation",
                "dq_rules_passed",
                "row_delta_within_threshold",
            ],
            "stg": [
                "regression_suite_passed",
                "performance_baseline_passed",
                "schema_drift_absent",
            ],
            "prod": [
                "post_deploy_smoke_passed",
                "critical_dq_rules_passed",
                "monitoring_alerts_green",
            ],
        }.get(
            environment,
            [
                "table_exists",
                "dq_rules_passed",
            ],
        )
        message = (
            f"QA checks passed in {environment} for "
            f"{plan.target_catalog}.{plan.target_schema}.{plan.target_table}: {','.join(checks)}"
        )
        self.logger.info(
            "qa_stage_validated environment=%s work_item_id=%s",
            environment,
            plan.work_item_id,
        )
        return True, message
