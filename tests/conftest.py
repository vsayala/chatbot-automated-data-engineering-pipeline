"""Shared pytest fixtures for agentic pipeline tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentic_de_pipeline.config import AppConfig


@pytest.fixture()
def test_config(tmp_path: Path) -> AppConfig:
    """Build isolated local config for tests."""
    return AppConfig.model_validate(
        {
            "local_mode": True,
            "azure_devops": {
                "organization_url": "https://dev.azure.com/test-org",
                "project": "test-project",
                "personal_access_token_env": "AZDO_PAT",
                "mock_data_path": "sample_data/work_items.json",
            },
            "azure_pipelines": {
                "organization_url": "https://dev.azure.com/test-org",
                "project": "test-project",
                "pipeline_name_prefix": "de-cicd",
                "personal_access_token_env": "AZDO_PAT",
            },
            "databricks": {
                "workspace_urls": {
                    "dev": "https://adb-dev.azuredatabricks.net",
                    "qe": "https://adb-qe.azuredatabricks.net",
                    "stg": "https://adb-stg.azuredatabricks.net",
                    "prod": "https://adb-prod.azuredatabricks.net",
                },
                "token_env": "DATABRICKS_TOKEN",
                "job_yaml_folder": str(tmp_path / "jobs"),
            },
            "approvals": {
                "mode": "auto",
                "timeout_seconds": 1,
                "auto_approve_stages": ["dev", "qe", "stg", "prod"],
                "state_file": str(tmp_path / "approvals.json"),
            },
            "logging": {
                "log_dir": str(tmp_path / "logs"),
                "log_level": "INFO",
            },
            "runtime": {
                "poll_interval_seconds": 1,
                "max_work_items_per_run": 1,
            },
            "learning_store_path": str(tmp_path / "learning.json"),
        }
    )
