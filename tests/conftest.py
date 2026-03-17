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
            "integration_mode": "simulate",
            "deployment_strategy": "dev_first_promotion",
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
            "azure_repos": {
                "organization_url": "https://dev.azure.com/test-org",
                "project": "test-project",
                "repository_name": "test-repo",
                "repository_url": "https://dev.azure.com/test-org/test-project/_git/test-repo",
                "default_base_branch": "main",
                "branch_prefix": "feature/pbi-",
                "local_checkout_path": str(tmp_path),
                "personal_access_token_env": "AZDO_PAT",
                "dry_run": True,
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
            "prompts": {
                "enabled": True,
                "templates_path": "config/prompts.yaml",
                "llm_enabled": False,
                "llm_provider": "ollama",
                "llm_model": "qwen2.5:14b-instruct",
                "llm_requires_api_key": False,
            },
            "mcp": {
                "enabled": False,
                "servers": {},
                "server_tokens": {},
                "request_timeout_seconds": 2,
            },
            "security": {
                "strict_private_mode": False,
                "enforce_internal_llm_endpoint": True,
                "enforce_internal_mcp_endpoints": True,
                "internal_hostname_suffixes": ["localhost", "127.0.0.1", ".local"],
                "allow_private_ip_ranges": True,
            },
            "workflow": {
                "stage_sequence": ["dev", "qe", "stg", "prod"],
                "databricks_apply_in_stages": ["dev"],
                "hil_approval_stages": ["qe", "stg", "prod"],
                "hil_approval_for_repo_actions": True,
            },
            "runtime": {
                "poll_interval_seconds": 1,
                "max_work_items_per_run": 1,
                "enable_repo_automation": True,
                "run_basic_tests": False,
                "basic_test_command": "python3 -m pytest -q tests/unit",
                "auto_create_pr": True,
                "require_preflight_before_run": False,
                "fail_fast": True,
                "enable_idempotency": True,
                "idempotency_store_path": str(tmp_path / "idempotency.json"),
                "retry_attempts": 2,
                "retry_initial_delay_seconds": 0.01,
                "retry_max_delay_seconds": 0.02,
                "retry_backoff_multiplier": 2.0,
                "fail_on_mcp_error": False,
                "enable_failure_remediation": True,
                "max_failure_remediation_attempts": 1,
                "require_hil_approval_for_remediation": True,
            },
            "learning_store_path": str(tmp_path / "learning.json"),
        }
    )
