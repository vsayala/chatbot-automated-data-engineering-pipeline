"""Configuration loading and validation utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


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
    local_checkout_root: str = "."
    allow_multi_repo_routing: bool = True
    auto_create_repository_if_missing: bool = True
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
        """Ensure at least one workspace URL is configured."""
        if not value:
            raise ValueError("At least one Databricks workspace URL must be configured.")
        return value


class WorkflowConfig(BaseModel):
    """Workflow stage and gate behavior controls."""

    stage_sequence: list[str] = Field(default_factory=lambda: ["dev", "qe", "stg", "prod"])
    databricks_apply_in_stages: list[str] = Field(default_factory=lambda: ["dev"])
    hil_approval_stages: list[str] = Field(default_factory=lambda: ["qe", "stg", "prod"])
    hil_approval_for_repo_actions: bool = True


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
    llm_provider: Literal["ollama", "openai_compatible"] = "ollama"
    llm_model: str = "qwen2.5:14b-instruct"
    llm_requires_api_key: bool = False
    llm_api_key_env: str = "LLM_API_KEY"
    llm_api_key: str | None = None


class MCPConfig(BaseModel):
    """Model Context Protocol connector settings."""

    enabled: bool = False
    servers: dict[str, str] = Field(default_factory=dict)
    server_tokens: dict[str, str] = Field(default_factory=dict)
    request_timeout_seconds: int = 30


class SecurityConfig(BaseModel):
    """Security guardrails for private deployment profiles."""

    strict_private_mode: bool = False
    enforce_internal_llm_endpoint: bool = True
    enforce_internal_mcp_endpoints: bool = True
    internal_hostname_suffixes: list[str] = Field(
        default_factory=lambda: [
            "localhost",
            "127.0.0.1",
            ".local",
            ".internal",
            ".corp",
            ".intranet",
        ]
    )
    allow_private_ip_ranges: bool = True
    enforce_allowed_egress_hosts: bool = True
    allowed_egress_hostname_suffixes: list[str] = Field(
        default_factory=lambda: [
            "dev.azure.com",
            ".azuredatabricks.net",
            "localhost",
            "127.0.0.1",
            ".local",
            ".internal",
            ".corp",
            ".intranet",
        ]
    )


class RuntimeConfig(BaseModel):
    """Runtime behavior controls."""

    poll_interval_seconds: int = 30
    max_work_items_per_run: int = 1
    enable_repo_automation: bool = True
    run_basic_tests: bool = True
    basic_test_command: str = "python3 -m pytest -q tests/unit"
    auto_create_pr: bool = True
    require_preflight_before_run: bool = True
    fail_fast: bool = True
    enable_idempotency: bool = True
    idempotency_store_path: str = "state/idempotency_state.json"
    retry_attempts: int = 3
    retry_initial_delay_seconds: float = 1.0
    retry_max_delay_seconds: float = 8.0
    retry_backoff_multiplier: float = 2.0
    fail_on_mcp_error: bool = False
    enable_failure_remediation: bool = True
    max_failure_remediation_attempts: int = 2
    require_hil_approval_for_remediation: bool = True


class TransformerConfig(BaseModel):
    """Repo-specific remediation transformer settings."""

    enabled: bool = True
    enabled_plugins: list[str] = Field(
        default_factory=lambda: ["databricks_notebook", "sql", "python_etl"]
    )
    allow_fallback_artifact: bool = True

    @field_validator("enabled_plugins")
    @classmethod
    def validate_enabled_plugins(cls, value: list[str]) -> list[str]:
        """Ensure plugin names are non-empty strings."""
        normalized = [plugin.strip() for plugin in value if plugin.strip()]
        if not normalized:
            raise ValueError("transformers.enabled_plugins must include at least one plugin name.")
        return normalized


class AppConfig(BaseModel):
    """Top-level application configuration schema."""

    app_name: str = "agentic-data-engineering-cicd"
    integration_mode: Literal["simulate", "connected"] = "simulate"
    deployment_strategy: str = "dev_first_promotion"
    # Backward-compatible alias for older configs; prefer integration_mode.
    local_mode: bool | None = None
    azure_devops: AzureDevOpsConfig = Field(default_factory=AzureDevOpsConfig)
    azure_pipelines: AzurePipelinesConfig = Field(default_factory=AzurePipelinesConfig)
    azure_repos: AzureReposConfig = Field(default_factory=AzureReposConfig)
    databricks: DatabricksConfig
    approvals: ApprovalConfig = Field(default_factory=ApprovalConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    prompts: PromptConfig = Field(default_factory=PromptConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    transformers: TransformerConfig = Field(default_factory=TransformerConfig)
    learning_store_path: str = "state/learning_memory.json"

    @model_validator(mode="after")
    def validate_cross_field_settings(self) -> "AppConfig":
        """Validate cross-field settings for safer runtime behavior."""
        if self.local_mode is not None:
            self.integration_mode = "simulate" if self.local_mode else "connected"

        stage_set = set(self.workflow.stage_sequence)
        missing_databricks_stages = set(self.workflow.databricks_apply_in_stages) - stage_set
        if missing_databricks_stages:
            raise ValueError(
                "workflow.databricks_apply_in_stages must be subset of workflow.stage_sequence. "
                f"Invalid stages: {sorted(missing_databricks_stages)}"
            )

        missing_hil_stages = set(self.workflow.hil_approval_stages) - stage_set
        if missing_hil_stages:
            raise ValueError(
                "workflow.hil_approval_stages must be subset of workflow.stage_sequence. "
                f"Invalid stages: {sorted(missing_hil_stages)}"
            )

        if self.runtime.retry_attempts < 1:
            raise ValueError("runtime.retry_attempts must be at least 1.")
        if self.runtime.retry_initial_delay_seconds <= 0:
            raise ValueError("runtime.retry_initial_delay_seconds must be greater than 0.")
        if self.runtime.retry_max_delay_seconds <= 0:
            raise ValueError("runtime.retry_max_delay_seconds must be greater than 0.")
        if self.runtime.retry_backoff_multiplier < 1:
            raise ValueError("runtime.retry_backoff_multiplier must be >= 1.")
        if self.runtime.max_failure_remediation_attempts < 0:
            raise ValueError("runtime.max_failure_remediation_attempts must be >= 0.")

        if self.security.strict_private_mode:
            if self.integration_mode != "connected":
                raise ValueError(
                    "security.strict_private_mode requires integration_mode='connected' "
                    "so the agent runs with real enterprise integrations."
                )
            if self.prompts.llm_enabled and not self.prompts.llm_endpoint_url:
                raise ValueError(
                    "security.strict_private_mode with llm_enabled=true requires prompts.llm_endpoint_url."
                )
        return self

    def is_simulate_mode(self) -> bool:
        """Return True when running in simulation integration mode."""
        return self.integration_mode == "simulate"


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
