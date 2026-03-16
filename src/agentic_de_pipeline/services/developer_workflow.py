"""Developer-level repo workflow automation before environment promotions."""

from __future__ import annotations

from pathlib import Path

from agentic_de_pipeline.adapters.azure_repos import AzureReposClient
from agentic_de_pipeline.logging_utils import get_module_logger
from agentic_de_pipeline.models import RequirementPlan, WorkItem


class DeveloperWorkflowService:
    """Handles branch/test/PR cycle for each selected work item."""

    def __init__(self, repos_client: AzureReposClient, log_dir: str) -> None:
        self.repos_client = repos_client
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
            configured_repo = self.repos_client.repo_config.repository_name
            if plan.target_repo != configured_repo:
                message = (
                    f"target_repo={plan.target_repo} does not match configured repository={configured_repo}. "
                    "Update azure_repos.repository_name/local_checkout_path or add repo routing support."
                )
                if self.repos_client.repo_config.dry_run:
                    self.logger.warning("developer_workflow_repo_mismatch %s", message)
                else:
                    return "failed", message

            branch_name = self.repos_client.prepare_branch(work_item)
            change_file = "dry-run/no-change-file"
            if not self.repos_client.repo_config.dry_run:
                change_file = self._write_work_item_change_stub(work_item, plan)

            tests_passed, test_output = self.repos_client.run_basic_tests()
            if not tests_passed:
                return "failed", f"basic tests failed on branch={branch_name}. output={test_output}"

            branch_name = self.repos_client.commit_and_push(work_item)
            pr_url = self.repos_client.create_pull_request(work_item, branch_name)
            detail = f"branch={branch_name}; change_file={change_file}; tests=passed; pr={pr_url}"
            self.logger.info("developer_workflow_completed work_item_id=%s", work_item.id)
            return "succeeded", detail
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.exception("developer_workflow_failed work_item_id=%s", work_item.id)
            return "failed", str(exc)

    @staticmethod
    def _write_work_item_change_stub(work_item: WorkItem, plan: RequirementPlan) -> str:
        """Create local code artifact documenting automated work-item changes."""
        folder = Path("generated_changes")
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
