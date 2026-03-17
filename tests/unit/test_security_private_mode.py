"""Unit tests for strict private mode behavior."""

from __future__ import annotations

import pytest

from agentic_de_pipeline.config import AppConfig
from agentic_de_pipeline.services.mcp_router import MCPRouter
from agentic_de_pipeline.services.preflight import PreflightValidator
from agentic_de_pipeline.utils.retry import RetryPolicy


def test_strict_private_mode_requires_connected_integration() -> None:
    """Configuration should reject strict private mode with simulate integration mode."""
    with pytest.raises(ValueError):
        AppConfig.model_validate(
            {
                "integration_mode": "simulate",
                "security": {"strict_private_mode": True},
                "databricks": {"workspace_urls": {"dev": "https://adb-dev.example.net"}},
            }
        )


def test_preflight_blocks_non_internal_llm_in_strict_mode(test_config) -> None:
    """Preflight should fail when strict mode uses external LLM endpoint."""
    test_config.integration_mode = "connected"
    test_config.security.strict_private_mode = True
    test_config.prompts.llm_enabled = True
    test_config.prompts.llm_endpoint_url = "https://external-llm.example.com/v1/chat/completions"
    validator = PreflightValidator(
        config=test_config,
        mcp_router=MCPRouter(test_config.mcp, test_config.logging.log_dir),
        retry_policy=RetryPolicy(attempts=1),
    )

    assert validator._check_llm() == "error(llm_endpoint_not_internal)"  # noqa: SLF001


def test_preflight_allows_no_api_key_for_internal_ollama(test_config) -> None:
    """Internal Ollama endpoint should pass without API key when not required."""
    test_config.integration_mode = "connected"
    test_config.security.strict_private_mode = True
    test_config.prompts.llm_enabled = True
    test_config.prompts.llm_endpoint_url = "http://127.0.0.1:11434/v1/chat/completions"
    test_config.prompts.llm_requires_api_key = False
    test_config.prompts.llm_api_key = None
    validator = PreflightValidator(
        config=test_config,
        mcp_router=MCPRouter(test_config.mcp, test_config.logging.log_dir),
        retry_policy=RetryPolicy(attempts=1),
    )

    assert validator._check_llm() == "ok"  # noqa: SLF001


def test_security_check_blocks_disallowed_egress_host(test_config) -> None:
    """Strict mode should fail when configured endpoints are outside allowed suffix list."""
    test_config.integration_mode = "connected"
    test_config.security.strict_private_mode = True
    test_config.azure_repos.organization_url = "https://malicious.example.com"
    validator = PreflightValidator(
        config=test_config,
        mcp_router=MCPRouter(test_config.mcp, test_config.logging.log_dir),
        retry_policy=RetryPolicy(attempts=1),
    )

    assert validator._check_security().startswith("error(disallowed_egress_hosts:")  # noqa: SLF001
