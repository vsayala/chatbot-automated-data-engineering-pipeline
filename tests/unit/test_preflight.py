"""Unit tests for preflight validation in simulate mode."""

from __future__ import annotations

from agentic_de_pipeline.services.mcp_router import MCPRouter
from agentic_de_pipeline.services.preflight import PreflightValidator
from agentic_de_pipeline.utils.retry import RetryPolicy


def test_preflight_simulate_mode_reports_ok_checks(test_config) -> None:
    """Simulate-mode preflight should pass with mock and dry-run settings."""
    validator = PreflightValidator(
        config=test_config,
        mcp_router=MCPRouter(test_config.mcp, test_config.logging.log_dir),
        retry_policy=RetryPolicy(attempts=1),
    )

    checks = validator.run_checks()

    assert checks["azure_devops"].startswith("ok")
    assert checks["azure_repos"].startswith("ok")
    assert checks["azure_pipelines"].startswith("ok")
    assert checks["databricks"].startswith("ok")
    assert checks["llm"].startswith("ok")
    assert checks["mcp"].startswith("ok")
    assert checks["security"].startswith("ok")
