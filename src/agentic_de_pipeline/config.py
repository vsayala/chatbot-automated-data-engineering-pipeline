"""Configuration loading and validation utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator


class AzureDevOpsConfig(BaseModel):
    """Settings for Azure DevOps Boards integration."""

    organization_url: str = "https://dev.azure.com/your-org"
    project: str = "data-engineering"
    board_url: str = "https://dev.azure.com/your-org/data-engineering/_boards/board"
    personal_access_token_env: str = "AZDO_PAT"
    personal_access_token: str | None = None
    mock_data_path: str = "sample_data/work_items.json"
    priority_field_name: str = "Microsoft.VSTS.Common.Priority"
    repo_hint_tag_prefix: str = "repo:"
    wiql_query: str = (
        "Select [System.Id], [System.Title], [System.WorkItemType], [Microsoft.VSTS.Common.Priority] "
        "From WorkItems "
        "Where [System.TeamProject] = @project "
        "And [System.WorkItemType] In ('Product Backlog Item', 'Bug', 'User Story') "
        "And [System.State] <> 'Closed' "
        "Order By [Microsoft.VSTS.Common.Priority] Asc, [System.ChangedDate] Desc"
    )


class AzurePipelinesConfig(BaseModel):
    """Settings for Azure Pipelines integration."""

    organization_url: str = "https://dev.azure.com/your-org"
    project: str = "data-engineering"
    pipeline_name_prefix: str = "de-cicd"
    pipeline_url: str = "https://dev.azure.com/your-org/data-engineering/_build"
    personal_access_token_env: str = "AZDO_PAT"
    personal_access_token: str | None = None


class AzureReposConfig(BaseModel):
    """Settings for Azure Repos branch/PR automation."""

    organization_url: str = "https://dev.azure.com/your-org"
    project: str = "data-engineering"
    repository_name: str = "data-engineering-repo"
    repository_url: str = "https://dev.azure.com/your-org/data-engineering/_git/data-engineering-repo"
    default_base_branch: str = "main"
    branch_prefix: str = "feature/pbi-"
    local_checkout_path: str = "."
    personal_access_token_env: str = "AZDO_PAT"
    personal_access_token: str | None = None
    dry_run: bool = True


class DatabricksConfig(BaseModel):
    """Databricks workspaces and authentication settings."""

    workspace_urls: dict[str, str] = Field(default_factory=dict)
    token_env: str = "DATABRICKS_TOKEN"
    token: str | None = None
    job_yaml_folder: str = "jobs"

    @field_validator("workspace_urls")
    @classmethod
    def validate_workspace_urls(cls, value: dict[str, str]) -> dict[str, str]:
        """Ensure required environments are configured."""
        required = {"dev", "qe", "stg", "prod"}
        missing = required - set(value)
        if missing:
            raise ValueError(f"Missing Databricks workspace URL for: {sorted(missing)}")
        return value


class ApprovalConfig(BaseModel):
    """Human approval controls."""

    mode: str = "console"
    timeout_seconds: int = 1800
    auto_approve_stages: list[str] = Field(default_factory=lambda: ["dev"])
    state_file: str = "state/approvals_state.json"


class LoggingConfig(BaseModel):
    """Logging folder and behavior."""

    log_dir: str = "logs"
    log_level: str = "INFO"


class PromptConfig(BaseModel):
    """Prompt templates and optional hosted LLM settings."""

    enabled: bool = True
    templates_path: str = "config/prompts.yaml"
    llm_enabled: bool = False
    llm_endpoint_url: str | None = None
    llm_model: str = "gpt-4o-mini"
    llm_api_key_env: str = "LLM_API_KEY"
    llm_api_key: str | None = None


class MCPConfig(BaseModel):
    """Model Context Protocol connector settings."""

    enabled: bool = False
    servers: dict[str, str] = Field(default_factory=dict)
    server_tokens: dict[str, str] = Field(default_factory=dict)


class RuntimeConfig(BaseModel):
    """Runtime behavior controls."""

    poll_interval_seconds: int = 30
    max_work_items_per_run: int = 1
    enable_repo_automation: bool = True
    run_basic_tests: bool = True
    basic_test_command: str = "python3 -m pytest -q tests/unit"
    auto_create_pr: bool = True


class AppConfig(BaseModel):
    """Top-level application configuration schema."""

    app_name: str = "agentic-data-engineering-cicd"
    local_mode: bool = True
    azure_devops: AzureDevOpsConfig = Field(default_factory=AzureDevOpsConfig)
    azure_pipelines: AzurePipelinesConfig = Field(default_factory=AzurePipelinesConfig)
    azure_repos: AzureReposConfig = Field(default_factory=AzureReposConfig)
    databricks: DatabricksConfig
    approvals: ApprovalConfig = Field(default_factory=ApprovalConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    prompts: PromptConfig = Field(default_factory=PromptConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    learning_store_path: str = "state/learning_memory.json"


def load_config(config_path: str | Path) -> AppConfig:
    """Load YAML configuration and validate it into AppConfig."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    raw_data: dict[str, Any]
    with path.open("r", encoding="utf-8") as file:
        raw_data = yaml.safe_load(file) or {}

    try:
        return AppConfig.model_validate(raw_data)
    except ValidationError as exc:
        raise ValueError(f"Invalid configuration: {exc}") from exc
