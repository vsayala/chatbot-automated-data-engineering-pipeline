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
    personal_access_token_env: str = "AZDO_PAT"
    query_id: str = ""
    mock_data_path: str = "sample_data/work_items.json"


class AzurePipelinesConfig(BaseModel):
    """Settings for Azure Pipelines integration."""

    organization_url: str = "https://dev.azure.com/your-org"
    project: str = "data-engineering"
    pipeline_name_prefix: str = "de-cicd"
    personal_access_token_env: str = "AZDO_PAT"


class DatabricksConfig(BaseModel):
    """Databricks workspaces and authentication settings."""

    workspace_urls: dict[str, str] = Field(default_factory=dict)
    token_env: str = "DATABRICKS_TOKEN"
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


class RuntimeConfig(BaseModel):
    """Runtime behavior controls."""

    poll_interval_seconds: int = 30
    max_work_items_per_run: int = 1


class AppConfig(BaseModel):
    """Top-level application configuration schema."""

    app_name: str = "agentic-data-engineering-cicd"
    local_mode: bool = True
    azure_devops: AzureDevOpsConfig = Field(default_factory=AzureDevOpsConfig)
    azure_pipelines: AzurePipelinesConfig = Field(default_factory=AzurePipelinesConfig)
    databricks: DatabricksConfig
    approvals: ApprovalConfig = Field(default_factory=ApprovalConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
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
