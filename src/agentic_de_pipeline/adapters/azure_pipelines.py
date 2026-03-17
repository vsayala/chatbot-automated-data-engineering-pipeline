"""Azure Pipelines adapter for CI/CD execution."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime

from agentic_de_pipeline.config import AppConfig
from agentic_de_pipeline.logging_utils import get_module_logger
from agentic_de_pipeline.models import PipelineRunResult, RequirementPlan
from agentic_de_pipeline.utils.retry import RetryPolicy, run_with_retry
from agentic_de_pipeline.utils.secrets import resolve_secret
from agentic_de_pipeline.utils.timing import timed_operation


class AzurePipelinesClient:
    """Triggers and monitors Azure Pipeline runs per environment."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.logger = get_module_logger(
            module_name="agentic_de_pipeline.azure_pipelines",
            log_dir=config.logging.log_dir,
            file_name="azure_pipelines.log",
        )
        self.retry_policy = RetryPolicy(
            attempts=config.runtime.retry_attempts,
            initial_delay_seconds=config.runtime.retry_initial_delay_seconds,
            max_delay_seconds=config.runtime.retry_max_delay_seconds,
            backoff_multiplier=config.runtime.retry_backoff_multiplier,
        )

    def run_cicd(self, environment: str, plan: RequirementPlan) -> PipelineRunResult:
        """Run CI/CD pipeline and return run metadata."""
        with timed_operation(self.logger, f"run_cicd_{environment}"):
            if self.config.is_simulate_mode():
                return self._simulate_pipeline(environment, plan)
            return self._trigger_real_pipeline(environment, plan)

    def _simulate_pipeline(self, environment: str, plan: RequirementPlan) -> PipelineRunResult:
        """Simulate pipeline run for local testing."""
        start = datetime.now(UTC)
        time.sleep(0.1)
        finish = datetime.now(UTC)
        run_id = f"local-{environment}-{plan.work_item_id}-{int(start.timestamp())}"
        status = "succeeded"
        self.logger.info(
            "local_pipeline_completed environment=%s run_id=%s status=%s",
            environment,
            run_id,
            status,
        )
        return PipelineRunResult(
            run_id=run_id,
            pipeline_name=f"local-{environment}",
            environment=environment,
            status=status,
            started_at=start,
            finished_at=finish,
            dashboard_url=f"http://localhost/pipelines/{run_id}",
        )

    def _trigger_real_pipeline(self, environment: str, plan: RequirementPlan) -> PipelineRunResult:
        """Trigger Azure Pipeline using REST and wait for completion."""
        import base64
        import urllib.request

        pat = resolve_secret(
            direct_value=self.config.azure_pipelines.personal_access_token,
            env_name=self.config.azure_pipelines.personal_access_token_env,
            secret_label="Azure DevOps PAT",
            required=True,
        )

        org_url = self.config.azure_pipelines.organization_url.rstrip("/")
        project = self.config.azure_pipelines.project
        pipeline_name = f"{self.config.azure_pipelines.pipeline_name_prefix}-{environment}"
        start = datetime.now(UTC)

        basic = base64.b64encode(f":{pat}".encode("utf-8")).decode("utf-8")
        headers = {
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/json",
        }

        # Resolve pipeline id from name.
        list_url = f"{org_url}/{project}/_apis/pipelines?api-version=7.0"
        list_req = urllib.request.Request(list_url, headers=headers, method="GET")

        def _fetch_pipelines() -> dict:
            with urllib.request.urlopen(list_req, timeout=30) as resp:  # nosec B310
                return json.loads(resp.read().decode("utf-8"))

        pipelines = run_with_retry(
            operation_name="azure_pipelines_list",
            action=_fetch_pipelines,
            policy=self.retry_policy,
            logger=self.logger,
        )

        pipeline_id = None
        for row in pipelines.get("value", []):
            if row.get("name") == pipeline_name:
                pipeline_id = row.get("id")
                break
        if not pipeline_id:
            raise RuntimeError(f"Pipeline not found: {pipeline_name}")

        trigger_url = f"{org_url}/{project}/_apis/pipelines/{pipeline_id}/runs?api-version=7.0"
        payload = {
            "templateParameters": {
                "workItemId": str(plan.work_item_id),
                "targetCatalog": plan.target_catalog,
                "targetSchema": plan.target_schema,
                "targetTable": plan.target_table,
                "ingestionMode": plan.ingestion_mode,
            }
        }
        trigger_req = urllib.request.Request(
            trigger_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        def _trigger_pipeline() -> dict:
            with urllib.request.urlopen(trigger_req, timeout=30) as resp:  # nosec B310
                return json.loads(resp.read().decode("utf-8"))

        run_data = run_with_retry(
            operation_name=f"azure_pipeline_trigger_{environment}",
            action=_trigger_pipeline,
            policy=self.retry_policy,
            logger=self.logger,
        )

        run_id = str(run_data["id"])
        run_url = f"{org_url}/{project}/_apis/pipelines/{pipeline_id}/runs/{run_id}?api-version=7.0"

        status = "inProgress"
        while status.lower() in {"inprogress", "notstarted"}:
            poll_req = urllib.request.Request(run_url, headers=headers, method="GET")

            def _poll_status() -> dict:
                with urllib.request.urlopen(poll_req, timeout=30) as resp:  # nosec B310
                    return json.loads(resp.read().decode("utf-8"))

            current = run_with_retry(
                operation_name=f"azure_pipeline_poll_{environment}",
                action=_poll_status,
                policy=self.retry_policy,
                logger=self.logger,
            )
            status = current.get("result") or current.get("state", "unknown")
            if status.lower() in {"inprogress", "notstarted"}:
                time.sleep(10)

        finish = datetime.now(UTC)
        self.logger.info(
            "azure_pipeline_completed environment=%s run_id=%s status=%s",
            environment,
            run_id,
            status,
        )
        return PipelineRunResult(
            run_id=run_id,
            pipeline_name=pipeline_name,
            environment=environment,
            status=status,
            started_at=start,
            finished_at=finish,
            dashboard_url=current.get("_links", {}).get("web", {}).get("href", ""),
        )

    # Production hardening (commented guidance):
    # ------------------------------------------------------------------
    # - Enforce managed identity + Key Vault secret retrieval for PAT/OAuth.
    # - Add policy checks for branch protection before trigger.
    # - Add vulnerability scanning gates and artifact provenance checks.
    # - Route logs to Azure Monitor / Log Analytics.
    # ------------------------------------------------------------------
