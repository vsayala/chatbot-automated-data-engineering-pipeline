"""Azure Repos adapter for branch and PR lifecycle automation."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from agentic_de_pipeline.config import AppConfig
from agentic_de_pipeline.logging_utils import get_module_logger
from agentic_de_pipeline.models import WorkItem
from agentic_de_pipeline.utils.retry import RetryPolicy, run_with_retry
from agentic_de_pipeline.utils.secrets import resolve_secret
from agentic_de_pipeline.utils.timing import timed_operation


class AzureReposClient:
    """Automates repository actions for PBI/bug/user-story implementation."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.repo_config = config.azure_repos
        self.runtime_config = config.runtime
        self.checkout_path = Path(self.repo_config.local_checkout_path).resolve()
        self.logger = get_module_logger(
            module_name="agentic_de_pipeline.azure_repos",
            log_dir=config.logging.log_dir,
            file_name="azure_repos.log",
        )
        self.retry_policy = RetryPolicy(
            attempts=config.runtime.retry_attempts,
            initial_delay_seconds=config.runtime.retry_initial_delay_seconds,
            max_delay_seconds=config.runtime.retry_max_delay_seconds,
            backoff_multiplier=config.runtime.retry_backoff_multiplier,
        )

    def prepare_branch(self, work_item: WorkItem) -> str:
        """Create or switch to work-item branch named with PBI/bug ID."""
        branch_name = self._build_branch_name(work_item.id, work_item.title)
        with timed_operation(self.logger, f"prepare_branch_{work_item.id}"):
            if self.repo_config.dry_run:
                self.logger.info("dry_run_branch_prepare branch=%s", branch_name)
                return branch_name

            self._run(["git", "fetch", "origin", self.repo_config.default_base_branch])
            self._run(["git", "checkout", self.repo_config.default_base_branch])
            self._run(["git", "pull", "origin", self.repo_config.default_base_branch])
            self._run(["git", "checkout", "-B", branch_name])
            self.logger.info("branch_prepared branch=%s", branch_name)
            return branch_name

    def run_basic_tests(self) -> tuple[bool, str]:
        """Run developer-level validation tests before CI trigger."""
        if not self.runtime_config.run_basic_tests:
            return True, "basic tests skipped by config"

        with timed_operation(self.logger, "run_basic_tests"):
            if self.repo_config.dry_run:
                return True, f"dry run: {self.runtime_config.basic_test_command}"

            result = subprocess.run(
                self.runtime_config.basic_test_command,
                cwd=self.checkout_path,
                shell=True,
                text=True,
                capture_output=True,
                check=False,
            )
            output = (result.stdout + "\n" + result.stderr).strip()
            passed = result.returncode == 0
            self.logger.info("basic_tests_completed passed=%s", passed)
            return passed, output

    def commit_and_push(self, work_item: WorkItem) -> str:
        """Commit and push changes to remote branch."""
        branch_name = self._build_branch_name(work_item.id, work_item.title)
        if self.repo_config.dry_run:
            self.logger.info("dry_run_commit_push branch=%s", branch_name)
            return branch_name

        self._run(["git", "add", "."])
        status = self._run(["git", "status", "--porcelain"])
        if not status.strip():
            self.logger.info("no_changes_to_commit")
            return branch_name

        commit_message = f"Implement work item {work_item.id}: {work_item.title}"
        self._run(["git", "commit", "-m", commit_message])
        self._run(["git", "push", "-u", "origin", branch_name])
        return branch_name

    def create_pull_request(self, work_item: WorkItem, branch_name: str) -> str:
        """Create Azure Repos pull request to target base branch."""
        if not self.runtime_config.auto_create_pr:
            return "PR creation disabled by runtime config"

        if self.repo_config.dry_run:
            return (
                f"dry-run-pr://{self.repo_config.repository_name}/"
                f"{branch_name}-to-{self.repo_config.default_base_branch}"
            )

        import base64
        import urllib.request

        pat = resolve_secret(
            direct_value=self.repo_config.personal_access_token,
            env_name=self.repo_config.personal_access_token_env,
            secret_label="Azure DevOps PAT",
            required=True,
        )
        basic = base64.b64encode(f":{pat}".encode("utf-8")).decode("utf-8")
        headers = {
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/json",
        }

        project = self.repo_config.project
        org_url = self.repo_config.organization_url.rstrip("/")
        repo_name = self.repo_config.repository_name
        url = f"{org_url}/{project}/_apis/git/repositories/{repo_name}/pullrequests?api-version=7.0"

        payload = {
            "sourceRefName": f"refs/heads/{branch_name}",
            "targetRefName": f"refs/heads/{self.repo_config.default_base_branch}",
            "title": f"Work Item {work_item.id}: {work_item.title}",
            "description": (
                f"Automated PR for work item {work_item.id}.\n"
                "Includes agent-generated data engineering CI/CD updates."
            ),
        }

        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        def _create_pr() -> dict:
            with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310
                return json.loads(response.read().decode("utf-8"))

        body = run_with_retry(
            operation_name=f"azure_repos_create_pr_{work_item.id}",
            action=_create_pr,
            policy=self.retry_policy,
            logger=self.logger,
        )

        pr_url = str(body.get("url", ""))
        self.logger.info("azure_repos_pr_created url=%s", pr_url)
        return pr_url

    def _build_branch_name(self, work_item_id: int, title: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        slug = slug[:35] if slug else "work-item"
        return f"{self.repo_config.branch_prefix}{work_item_id}-{slug}"

    def _run(self, args: list[str]) -> str:
        result = subprocess.run(
            args,
            cwd=self.checkout_path,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Command failed ({' '.join(args)}): {result.stderr.strip() or result.stdout.strip()}"
            )
        return result.stdout.strip()
