"""Developer-level repo workflow automation before environment promotions."""

from __future__ import annotations

from pathlib import Path

from agentic_de_pipeline.adapters.azure_repos import AzureReposClient
from agentic_de_pipeline.logging_utils import get_module_logger
from agentic_de_pipeline.models import RequirementPlan, WorkItem
from agentic_de_pipeline.transformers import RemediationContext, TransformerRegistry


class DeveloperWorkflowService:
    """Handles branch/test/PR cycle for each selected work item."""

    def __init__(
        self,
        repos_client: AzureReposClient,
        log_dir: str,
        transformer_registry: TransformerRegistry | None = None,
        transformers_enabled: bool = True,
        allow_fallback_artifact: bool = True,
    ) -> None:
        self.repos_client = repos_client
        self.transformer_registry = transformer_registry
        self.transformers_enabled = transformers_enabled
        self.allow_fallback_artifact = allow_fallback_artifact
        self.logger = get_module_logger(
            module_name="agentic_de_pipeline.developer_workflow",
            log_dir=log_dir,
            file_name="developer_workflow.log",
        )

    def execute(self, work_item: WorkItem, plan: RequirementPlan) -> tuple[str, str]:
        """Run developer workflow and return status details."""
        if not self.repos_client.runtime_config.enable_repo_automation:
            return "skipped", "Repository automation disabled in runtime config"

        try:
            ready, repo_msg = self.repos_client.ensure_repository(plan.target_repo)
            if not ready:
                return "failed", repo_msg

            branch_name = self.repos_client.prepare_branch(work_item, plan.target_repo)
            change_file = "dry-run/no-change-file"
            if not self.repos_client.repo_config.dry_run:
                change_file = self._write_work_item_change_stub(
                    work_item=work_item,
                    plan=plan,
                    repo_path=self.repos_client.get_checkout_path(plan.target_repo),
                )

            tests_passed, test_output = self.repos_client.run_basic_tests(plan.target_repo)
            if not tests_passed:
                return "failed", f"basic tests failed on branch={branch_name}. output={test_output}"

            branch_name = self.repos_client.commit_and_push(work_item, plan.target_repo)
            pr_url = self.repos_client.create_pull_request(work_item, branch_name, plan.target_repo)
            detail = (
                f"repo={plan.target_repo}; repo_status={repo_msg}; branch={branch_name}; "
                f"change_file={change_file}; tests=passed; pr={pr_url}"
            )
            self.logger.info("developer_workflow_completed work_item_id=%s", work_item.id)
            return "succeeded", detail
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.exception("developer_workflow_failed work_item_id=%s", work_item.id)
            return "failed", str(exc)

    def apply_remediation(
        self,
        work_item: WorkItem,
        plan: RequirementPlan,
        environment: str,
        failure_context: str,
        suggestion: str,
        attempt: int,
    ) -> tuple[str, str]:
        """Apply remediation code changes and rerun developer validation steps."""
        try:
            repo_path = self.repos_client.get_checkout_path(plan.target_repo)
            remediation_reference = ""
            if self.transformers_enabled and self.transformer_registry is not None:
                report = self.transformer_registry.apply(
                    RemediationContext(
                        work_item=work_item,
                        plan=plan,
                        environment=environment,
                        failure_context=failure_context,
                        suggestion=suggestion,
                        attempt=attempt,
                        repo_path=repo_path,
                    )
                )
                if report.was_changed:
                    remediation_reference = (
                        f"transformers={report.to_summary()}; "
                        f"changed_files={','.join(report.changed_files)}"
                    )

            if not remediation_reference:
                if not self.allow_fallback_artifact:
                    return "failed", "No remediation transformers applied and fallback artifact is disabled."
                artifact = self._write_remediation_artifact(
                    work_item=work_item,
                    plan=plan,
                    environment=environment,
                    suggestion=suggestion,
                    attempt=attempt,
                    repo_path=repo_path,
                )
                remediation_reference = f"remediation_artifact={artifact}"

            tests_passed, test_output = self.repos_client.run_basic_tests(plan.target_repo)
            if not tests_passed:
                return "failed", f"remediation tests failed: {test_output}"
            branch_name = self.repos_client.commit_and_push(work_item, plan.target_repo)
            detail = f"{remediation_reference}; branch={branch_name}; tests=passed"
            self.logger.info(
                "developer_remediation_completed work_item_id=%s environment=%s attempt=%s",
                work_item.id,
                environment,
                attempt,
            )
            return "succeeded", detail
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.exception(
                "developer_remediation_failed work_item_id=%s environment=%s attempt=%s",
                work_item.id,
                environment,
                attempt,
            )
            return "failed", str(exc)

    @staticmethod
    def _write_work_item_change_stub(
        work_item: WorkItem,
        plan: RequirementPlan,
        repo_path: Path,
    ) -> str:
        """Create local code artifact documenting automated work-item changes."""
        folder = repo_path / "generated_changes"
        folder.mkdir(parents=True, exist_ok=True)
        file_path = folder / f"work_item_{work_item.id}.md"
        file_path.write_text(
            "\n".join(
                [
                    f"# Work Item {work_item.id}",
                    f"Title: {work_item.title}",
                    f"Priority: {work_item.priority}",
                    f"Target Repo: {plan.target_repo}",
                    f"Branch: {plan.branch_name}",
                    f"Target Table: {plan.target_catalog}.{plan.target_schema}.{plan.target_table}",
                    f"Ingestion Mode: {plan.ingestion_mode}",
                    f"Source Types: {', '.join(plan.source_types)}",
                ]
            ),
            encoding="utf-8",
        )
        return str(file_path)

    @staticmethod
    def _write_remediation_artifact(
        work_item: WorkItem,
        plan: RequirementPlan,
        environment: str,
        suggestion: str,
        attempt: int,
        repo_path: Path,
    ) -> str:
        """Write remediation note artifact for traceability and review."""
        folder = repo_path / "generated_changes"
        folder.mkdir(parents=True, exist_ok=True)
        file_path = folder / f"remediation_{work_item.id}_{environment}_attempt_{attempt}.md"
        file_path.write_text(
            "\n".join(
                [
                    f"# Remediation for Work Item {work_item.id}",
                    f"Environment: {environment}",
                    f"Attempt: {attempt}",
                    f"Repo: {plan.target_repo}",
                    f"Target Table: {plan.target_catalog}.{plan.target_schema}.{plan.target_table}",
                    "Suggested Fix:",
                    suggestion,
                ]
            ),
            encoding="utf-8",
        )
        return str(file_path)
