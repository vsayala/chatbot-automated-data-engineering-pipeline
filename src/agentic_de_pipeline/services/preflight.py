"""Preflight connectivity validator for external services."""

from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path

from agentic_de_pipeline.config import AppConfig
from agentic_de_pipeline.logging_utils import get_module_logger
from agentic_de_pipeline.services.mcp_router import MCPRouter
from agentic_de_pipeline.utils.retry import RetryPolicy, run_with_retry
from agentic_de_pipeline.utils.secrets import resolve_secret


class PreflightValidator:
    """Runs fail-fast readiness checks before workflow execution."""

    def __init__(self, config: AppConfig, mcp_router: MCPRouter, retry_policy: RetryPolicy) -> None:
        self.config = config
        self.mcp_router = mcp_router
        self.retry_policy = retry_policy
        self.logger = get_module_logger(
            module_name="agentic_de_pipeline.preflight",
            log_dir=config.logging.log_dir,
            file_name="preflight.log",
        )

    def run_checks(self) -> dict[str, str]:
        """Run all preflight checks and return status map."""
        checks: dict[str, str] = {}
        checks["azure_devops"] = self._check_azure_devops()
        checks["azure_repos"] = self._check_azure_repos()
        checks["azure_pipelines"] = self._check_azure_pipelines()
        checks["databricks"] = self._check_databricks()
        checks["llm"] = self._check_llm()
        checks["mcp"] = self._check_mcp()
        return checks

    def validate_or_raise(self) -> dict[str, str]:
        """Run checks and raise on failures when fail_fast is enabled."""
        checks = self.run_checks()
        failed = {name: status for name, status in checks.items() if not status.startswith("ok")}
        if failed and self.config.runtime.fail_fast:
            raise RuntimeError(f"Preflight failed: {failed}")
        return checks

    def _check_azure_devops(self) -> str:
        if self.config.local_mode:
            mock_path = Path(self.config.azure_devops.mock_data_path)
            return "ok(local_mock_present)" if mock_path.exists() else "error(mock_data_missing)"

        pat = resolve_secret(
            direct_value=self.config.azure_devops.personal_access_token,
            env_name=self.config.azure_devops.personal_access_token_env,
            secret_label="Azure DevOps PAT",
            required=True,
        )
        import base64

        basic = base64.b64encode(f":{pat}".encode("utf-8")).decode("utf-8")
        headers = {"Authorization": f"Basic {basic}", "Content-Type": "application/json"}
        org_url = self.config.azure_devops.organization_url.rstrip("/")
        project = self.config.azure_devops.project
        url = f"{org_url}/{project}/_apis/wit/wiql?api-version=7.0"
        data = json.dumps({"query": "Select [System.Id] From WorkItems Where [System.Id] > 0"}).encode("utf-8")

        def _action() -> None:
            req = urllib.request.Request(url=url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30):  # nosec B310
                return None

        run_with_retry("preflight_azure_devops", _action, self.retry_policy, self.logger)
        return "ok"

    def _check_azure_repos(self) -> str:
        checkout = Path(self.config.azure_repos.local_checkout_path)
        if not checkout.exists():
            return f"error(local_checkout_missing:{checkout})"

        if self.config.azure_repos.dry_run:
            return "ok(dry_run)"

        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=checkout,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            return f"error(git_repo_check_failed:{result.stderr.strip() or result.stdout.strip()})"
        return "ok"

    def _check_azure_pipelines(self) -> str:
        if self.config.local_mode:
            return "ok(local_mode)"

        pat = resolve_secret(
            direct_value=self.config.azure_pipelines.personal_access_token,
            env_name=self.config.azure_pipelines.personal_access_token_env,
            secret_label="Azure DevOps PAT",
            required=True,
        )
        import base64

        basic = base64.b64encode(f":{pat}".encode("utf-8")).decode("utf-8")
        headers = {"Authorization": f"Basic {basic}", "Content-Type": "application/json"}
        org_url = self.config.azure_pipelines.organization_url.rstrip("/")
        project = self.config.azure_pipelines.project
        url = f"{org_url}/{project}/_apis/pipelines?api-version=7.0"

        def _action() -> None:
            req = urllib.request.Request(url=url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=30):  # nosec B310
                return None

        run_with_retry("preflight_azure_pipelines", _action, self.retry_policy, self.logger)
        return "ok"

    def _check_databricks(self) -> str:
        stages = self.config.workflow.databricks_apply_in_stages
        missing = [stage for stage in stages if stage not in self.config.databricks.workspace_urls]
        if missing:
            return f"error(missing_workspace_urls:{','.join(missing)})"

        if self.config.local_mode:
            return "ok(local_mode)"

        token = resolve_secret(
            direct_value=self.config.databricks.token,
            env_name=self.config.databricks.token_env,
            secret_label="Databricks token",
            required=True,
        )

        for stage in stages:
            workspace_url = self.config.databricks.workspace_urls[stage].rstrip("/")
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            url = f"{workspace_url}/api/2.0/clusters/list"

            def _action() -> None:
                req = urllib.request.Request(url=url, headers=headers, method="GET")
                with urllib.request.urlopen(req, timeout=30):  # nosec B310
                    return None

            run_with_retry(f"preflight_databricks_{stage}", _action, self.retry_policy, self.logger)
        return "ok"

    def _check_llm(self) -> str:
        if not self.config.prompts.llm_enabled:
            return "ok(disabled)"
        if not self.config.prompts.llm_endpoint_url:
            return "error(llm_endpoint_missing)"

        _ = resolve_secret(
            direct_value=self.config.prompts.llm_api_key,
            env_name=self.config.prompts.llm_api_key_env,
            secret_label="LLM API key",
            required=True,
        )
        return "ok"

    def _check_mcp(self) -> str:
        status = self.mcp_router.ping_all(self.retry_policy)
        if not self.config.mcp.enabled:
            return "ok(disabled)"
        failures = [name for name, value in status.items() if not value.startswith("reachable")]
        if failures:
            return f"error(unreachable_servers:{','.join(failures)})"
        return "ok"
