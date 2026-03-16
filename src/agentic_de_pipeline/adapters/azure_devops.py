"""Azure DevOps Boards adapter with local mock fallback."""

from __future__ import annotations

import json
from pathlib import Path

from agentic_de_pipeline.config import AppConfig
from agentic_de_pipeline.logging_utils import get_module_logger
from agentic_de_pipeline.models import WorkItem, WorkItemType
from agentic_de_pipeline.utils.secrets import resolve_secret
from agentic_de_pipeline.utils.timing import timed_operation


class AzureDevOpsClient:
    """Fetches PBIs, bugs, and user stories from Azure DevOps."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.logger = get_module_logger(
            module_name="agentic_de_pipeline.azure_devops",
            log_dir=config.logging.log_dir,
            file_name="azure_devops.log",
        )

    def fetch_open_work_items(self, limit: int = 5) -> list[WorkItem]:
        """Fetch work items either from local mock or Azure DevOps."""
        with timed_operation(self.logger, "fetch_open_work_items"):
            if self.config.local_mode:
                return self._load_mock_work_items(limit=limit)
            return self._fetch_from_azure_devops(limit=limit)

    def _load_mock_work_items(self, limit: int) -> list[WorkItem]:
        """Load mock work items for local development and sort by priority."""
        path = Path(self.config.azure_devops.mock_data_path)
        if not path.exists():
            self.logger.warning("mock_work_items_missing path=%s", path)
            return []

        rows = json.loads(path.read_text(encoding="utf-8"))
        normalized: list[WorkItem] = []
        for row in rows:
            item_type = WorkItemType(row.get("item_type", WorkItemType.USER_STORY.value))
            tags = [str(tag) for tag in row.get("tags", [])]
            repo_name = str(row.get("repo_name", "")).strip() or self._extract_repo_name(tags)
            normalized.append(
                WorkItem(
                    id=int(row["id"]),
                    title=str(row["title"]),
                    description=str(row.get("description", "")),
                    item_type=item_type,
                    tags=tags,
                    acceptance_criteria=str(row.get("acceptance_criteria", "")),
                    priority=int(row.get("priority", 9999)),
                    repo_name=repo_name,
                )
            )

        ranked = sorted(normalized, key=lambda item: (item.priority, item.id))
        selected = ranked[:limit]
        self.logger.info("mock_work_items_loaded count=%s", len(selected))
        return selected

    def _fetch_from_azure_devops(self, limit: int) -> list[WorkItem]:
        """Fetch work items from Azure DevOps REST API using priority ranking."""
        import base64
        import urllib.request

        pat = resolve_secret(
            direct_value=self.config.azure_devops.personal_access_token,
            env_name=self.config.azure_devops.personal_access_token_env,
            secret_label="Azure DevOps PAT",
            required=True,
        )

        org_url = self.config.azure_devops.organization_url.rstrip("/")
        project = self.config.azure_devops.project
        priority_field = self.config.azure_devops.priority_field_name

        wiql_payload = json.dumps({"query": self.config.azure_devops.wiql_query}).encode("utf-8")
        basic = base64.b64encode(f":{pat}".encode("utf-8")).decode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {basic}",
        }

        wiql_url = f"{org_url}/{project}/_apis/wit/wiql?api-version=7.0"
        req = urllib.request.Request(wiql_url, data=wiql_payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310
            wiql_result = json.loads(resp.read().decode("utf-8"))

        ids = [str(item["id"]) for item in wiql_result.get("workItems", [])[:limit]]
        if not ids:
            return []

        detail_url = (
            f"{org_url}/{project}/_apis/wit/workitems"
            f"?ids={','.join(ids)}"
            "&fields=System.Id,System.Title,System.Description,System.WorkItemType,System.Tags,"
            f"Microsoft.VSTS.Common.AcceptanceCriteria,{priority_field}"
            "&api-version=7.0"
        )
        detail_req = urllib.request.Request(detail_url, headers=headers, method="GET")
        with urllib.request.urlopen(detail_req, timeout=30) as resp:  # nosec B310
            detail_result = json.loads(resp.read().decode("utf-8"))

        output: list[WorkItem] = []
        for row in detail_result.get("value", []):
            fields = row.get("fields", {})
            type_value = fields.get("System.WorkItemType", WorkItemType.USER_STORY.value)
            try:
                item_type = WorkItemType(type_value)
            except ValueError:
                item_type = WorkItemType.USER_STORY

            tags = [tag.strip() for tag in fields.get("System.Tags", "").split(";") if tag.strip()]
            repo_name = self._extract_repo_name(tags)
            output.append(
                WorkItem(
                    id=int(fields["System.Id"]),
                    title=str(fields.get("System.Title", "")),
                    description=str(fields.get("System.Description", "")),
                    item_type=item_type,
                    tags=tags,
                    acceptance_criteria=str(fields.get("Microsoft.VSTS.Common.AcceptanceCriteria", "")),
                    priority=int(fields.get(priority_field, 9999)),
                    repo_name=repo_name,
                )
            )

        ranked = sorted(output, key=lambda item: (item.priority, item.id))
        self.logger.info("azure_devops_work_items_loaded count=%s", len(ranked))
        return ranked[:limit]

    def _extract_repo_name(self, tags: list[str]) -> str | None:
        """Extract repository hint from tags such as repo:analytics-platform."""
        prefix = self.config.azure_devops.repo_hint_tag_prefix.lower().strip()
        for tag in tags:
            tag_clean = tag.strip()
            if tag_clean.lower().startswith(prefix):
                return tag_clean[len(prefix) :].strip() or None
        return None

    # Production SDK option (disabled/commented intentionally):
    # ------------------------------------------------------------------
    # To use Azure DevOps Python SDK in enterprise environments:
    # 1) install dependency: pip install azure-devops
    # 2) enable secure PAT retrieval from Key Vault / managed identity
    # 3) replace REST calls with SDK client usage below.
    # ------------------------------------------------------------------
