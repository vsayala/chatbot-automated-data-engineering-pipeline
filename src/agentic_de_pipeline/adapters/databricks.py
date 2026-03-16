"""Databricks workspace adapter for Unity Catalog changes."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from agentic_de_pipeline.config import AppConfig
from agentic_de_pipeline.logging_utils import get_module_logger
from agentic_de_pipeline.models import RequirementPlan, StageResult
from agentic_de_pipeline.utils.timing import timed_operation


class DatabricksWorkspaceClient:
    """Executes notebook/job specs for table creation and ingestion flows."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.logger = get_module_logger(
            module_name="agentic_de_pipeline.databricks",
            log_dir=config.logging.log_dir,
            file_name="databricks.log",
        )

    def apply_plan(self, environment: str, plan: RequirementPlan) -> StageResult:
        """Apply plan in target workspace environment."""
        with timed_operation(self.logger, f"databricks_apply_{environment}"):
            start = datetime.now(UTC)
            if self.config.local_mode:
                details = self._simulate_apply(environment=environment, plan=plan)
                status = "succeeded"
            else:
                details = self._execute_notebook_job(environment=environment, plan=plan)
                status = "succeeded"
            finish = datetime.now(UTC)
            return StageResult(
                environment=environment,
                status=status,
                details=details,
                started_at=start,
                finished_at=finish,
            )

    def _simulate_apply(self, environment: str, plan: RequirementPlan) -> str:
        """Simulate Databricks operations by writing local artifact."""
        jobs_folder = Path(self.config.databricks.job_yaml_folder)
        jobs_folder.mkdir(parents=True, exist_ok=True)
        path = jobs_folder / f"{environment}_work_item_{plan.work_item_id}.yaml"
        content = (
            f"# local simulation artifact\n"
            f"work_item_id: {plan.work_item_id}\n"
            f"environment: {environment}\n"
            f"target_table: {plan.target_catalog}.{plan.target_schema}.{plan.target_table}\n"
            f"ingestion_mode: {plan.ingestion_mode}\n"
            f"notebook_tasks:\n"
        )
        for task in plan.notebook_tasks:
            content += f"  - {task}\n"
        path.write_text(content, encoding="utf-8")
        self.logger.info("local_databricks_artifact_created path=%s", path)
        return f"Local Databricks simulation completed. Job spec written to {path}."

    def _execute_notebook_job(self, environment: str, plan: RequirementPlan) -> str:
        """Execute Databricks notebook job using REST APIs."""
        import json
        import urllib.request

        token_env = self.config.databricks.token_env
        token = os.getenv(token_env)
        if not token:
            raise RuntimeError(f"Missing Databricks token in env var: {token_env}")

        workspace_url = self.config.databricks.workspace_urls[environment].rstrip("/")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        notebook_task_path = "/Shared/agentic/table_ingestion"
        payload = {
            "name": f"agentic-{environment}-{plan.work_item_id}",
            "tasks": [
                {
                    "task_key": "create_and_ingest_table",
                    "notebook_task": {
                        "notebook_path": notebook_task_path,
                        "base_parameters": {
                            "target_catalog": plan.target_catalog,
                            "target_schema": plan.target_schema,
                            "target_table": plan.target_table,
                            "ingestion_mode": plan.ingestion_mode,
                        },
                    },
                    "existing_cluster_id": "<REPLACE_WITH_SECURE_CLUSTER_ID>",
                }
            ],
        }

        create_url = f"{workspace_url}/api/2.1/jobs/create"
        create_req = urllib.request.Request(
            create_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(create_req, timeout=30) as resp:  # nosec B310
            create_data = json.loads(resp.read().decode("utf-8"))

        job_id = create_data["job_id"]
        run_url = f"{workspace_url}/api/2.1/jobs/run-now"
        run_payload = {"job_id": job_id}
        run_req = urllib.request.Request(
            run_url,
            data=json.dumps(run_payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(run_req, timeout=30) as resp:  # nosec B310
            run_data = json.loads(resp.read().decode("utf-8"))

        run_id = run_data["run_id"]
        self.logger.info(
            "databricks_job_triggered environment=%s job_id=%s run_id=%s",
            environment,
            job_id,
            run_id,
        )
        return f"Triggered Databricks job_id={job_id}, run_id={run_id} for environment={environment}."

    # Production SDK option (disabled/commented intentionally):
    # ------------------------------------------------------------------
    # To enable Databricks SDK usage:
    # 1) pip install databricks-sdk
    # 2) Configure OAuth service principal with least privilege
    # 3) Replace REST invocation with WorkspaceClient usage.
    #
    # from databricks.sdk import WorkspaceClient
    # w = WorkspaceClient(host=workspace_url, token=token)
    # ...
    # ------------------------------------------------------------------
