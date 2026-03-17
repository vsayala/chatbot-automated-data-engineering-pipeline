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
        self.checkout_root = Path(self.repo_config.local_checkout_root).resolve()
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

    def ensure_repository(self, repo_name: str) -> tuple[bool, str]:
        """Ensure target repository exists and local checkout is available."""
        with timed_operation(self.logger, f"ensure_repository_{repo_name}"):
            if self.repo_config.dry_run:
                if repo_name != self.repo_config.repository_name and self.repo_config.auto_create_repository_if_missing:
                    return True, f"dry-run-created-repo:{repo_name}"
                return True, f"dry-run-existing-repo:{repo_name}"

            exists = self._repository_exists_remote(repo_name)
            if not exists:
                if not self.repo_config.auto_create_repository_if_missing:
                    return False, f"repository_missing:{repo_name}"
                self._create_repository_remote(repo_name)

            checkout_path = self._resolve_checkout_path(repo_name)
            if not checkout_path.exists() or not (checkout_path / ".git").exists():
                self._clone_repository(repo_name, checkout_path)
            return True, f"repository_ready:{repo_name}"

    def prepare_branch(self, work_item: WorkItem, repo_name: str) -> str:
        """Create or switch to work-item branch named with PBI/bug ID."""
        branch_name = self._build_branch_name(work_item.id, work_item.title)
        with timed_operation(self.logger, f"prepare_branch_{work_item.id}"):
            if self.repo_config.dry_run:
                self.logger.info("dry_run_branch_prepare repo=%s branch=%s", repo_name, branch_name)
                return branch_name

            checkout_path = self._resolve_checkout_path(repo_name)
            self._run(["git", "fetch", "origin", self.repo_config.default_base_branch], checkout_path)
            self._run(["git", "checkout", self.repo_config.default_base_branch], checkout_path)
            self._run(["git", "pull", "origin", self.repo_config.default_base_branch], checkout_path)
            self._run(["git", "checkout", "-B", branch_name], checkout_path)
            self.logger.info("branch_prepared repo=%s branch=%s", repo_name, branch_name)
            return branch_name

    def run_basic_tests(self, repo_name: str) -> tuple[bool, str]:
        """Run developer-level validation tests before CI trigger."""
        if not self.runtime_config.run_basic_tests:
            return True, "basic tests skipped by config"

        with timed_operation(self.logger, f"run_basic_tests_{repo_name}"):
            if self.repo_config.dry_run:
                return True, f"dry run: {self.runtime_config.basic_test_command}"

            checkout_path = self._resolve_checkout_path(repo_name)
            result = subprocess.run(
                self.runtime_config.basic_test_command,
                cwd=checkout_path,
                shell=True,
                text=True,
                capture_output=True,
                check=False,
            )
            output = (result.stdout + "\n" + result.stderr).strip()
            passed = result.returncode == 0
            self.logger.info("basic_tests_completed repo=%s passed=%s", repo_name, passed)
            return passed, output

    def commit_and_push(self, work_item: WorkItem, repo_name: str) -> str:
        """Commit and push changes to remote branch."""
        branch_name = self._build_branch_name(work_item.id, work_item.title)
        if self.repo_config.dry_run:
            self.logger.info("dry_run_commit_push repo=%s branch=%s", repo_name, branch_name)
            return branch_name

        checkout_path = self._resolve_checkout_path(repo_name)
        self._run(["git", "add", "."], checkout_path)
        status = self._run(["git", "status", "--porcelain"], checkout_path)
        if not status.strip():
            self.logger.info("no_changes_to_commit repo=%s", repo_name)
            return branch_name

        commit_message = f"Implement work item {work_item.id}: {work_item.title}"
        self._run(["git", "commit", "-m", commit_message], checkout_path)
        self._run(["git", "push", "-u", "origin", branch_name], checkout_path)
        return branch_name

    def create_pull_request(self, work_item: WorkItem, branch_name: str, repo_name: str) -> str:
        """Create Azure Repos pull request to target base branch."""
        if not self.runtime_config.auto_create_pr:
            return "PR creation disabled by runtime config"

        if self.repo_config.dry_run:
            return f"dry-run-pr://{repo_name}/{branch_name}-to-{self.repo_config.default_base_branch}"

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
        self.logger.info("azure_repos_pr_created repo=%s url=%s", repo_name, pr_url)
        return pr_url

    def _repository_exists_remote(self, repo_name: str) -> bool:
        import base64
        import urllib.error
        import urllib.request

        pat = resolve_secret(
            direct_value=self.repo_config.personal_access_token,
            env_name=self.repo_config.personal_access_token_env,
            secret_label="Azure DevOps PAT",
            required=True,
        )
        basic = base64.b64encode(f":{pat}".encode("utf-8")).decode("utf-8")
        headers = {"Authorization": f"Basic {basic}", "Content-Type": "application/json"}

        project = self.repo_config.project
        org_url = self.repo_config.organization_url.rstrip("/")
        url = f"{org_url}/{project}/_apis/git/repositories/{repo_name}?api-version=7.0"
        request = urllib.request.Request(url=url, headers=headers, method="GET")

        try:
            def _fetch_repo() -> None:
                with urllib.request.urlopen(request, timeout=30):  # nosec B310
                    return None
            run_with_retry(
                operation_name=f"azure_repos_exists_{repo_name}",
                action=_fetch_repo,
                policy=self.retry_policy,
                logger=self.logger,
            )
            return True
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return False
            raise

    def _create_repository_remote(self, repo_name: str) -> None:
        import base64
        import urllib.request

        pat = resolve_secret(
            direct_value=self.repo_config.personal_access_token,
            env_name=self.repo_config.personal_access_token_env,
            secret_label="Azure DevOps PAT",
            required=True,
        )
        basic = base64.b64encode(f":{pat}".encode("utf-8")).decode("utf-8")
        headers = {"Authorization": f"Basic {basic}", "Content-Type": "application/json"}

        project = self.repo_config.project
        org_url = self.repo_config.organization_url.rstrip("/")
        url = f"{org_url}/{project}/_apis/git/repositories?api-version=7.0"
        payload = json.dumps({"name": repo_name, "project": {"name": project}}).encode("utf-8")
        request = urllib.request.Request(url=url, data=payload, headers=headers, method="POST")

        def _create_repo() -> None:
            with urllib.request.urlopen(request, timeout=30):  # nosec B310
                return None

        run_with_retry(
            operation_name=f"azure_repos_create_{repo_name}",
            action=_create_repo,
            policy=self.retry_policy,
            logger=self.logger,
        )
        self.logger.info("repository_created repo=%s", repo_name)

    def _clone_repository(self, repo_name: str, checkout_path: Path) -> None:
        checkout_path.parent.mkdir(parents=True, exist_ok=True)
        repo_url = (
            f"{self.repo_config.organization_url.rstrip('/')}/"
            f"{self.repo_config.project}/_git/{repo_name}"
        )
        self._run(["git", "clone", repo_url, str(checkout_path)], self.checkout_root)
        self.logger.info("repository_cloned repo=%s path=%s", repo_name, checkout_path)

    def _resolve_checkout_path(self, repo_name: str) -> Path:
        if repo_name == self.repo_config.repository_name or not self.repo_config.allow_multi_repo_routing:
            return self.checkout_path
        return (self.checkout_root / repo_name).resolve()

    def get_checkout_path(self, repo_name: str) -> Path:
        """Return local checkout path for the given repository name."""
        return self._resolve_checkout_path(repo_name)

    def _build_branch_name(self, work_item_id: int, title: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        slug = slug[:35] if slug else "work-item"
        return f"{self.repo_config.branch_prefix}{work_item_id}-{slug}"

    def _run(self, args: list[str], cwd: Path) -> str:
        result = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Command failed ({' '.join(args)}): {result.stderr.strip() or result.stdout.strip()}"
            )
        return result.stdout.strip()
