"""Unit tests for runtime profile configuration semantics."""

from __future__ import annotations

from agentic_de_pipeline.config import AppConfig


def test_integration_mode_simulate_is_detected() -> None:
    """Config should expose simulate mode via helper."""
    config = AppConfig.model_validate(
        {
            "integration_mode": "simulate",
            "deployment_strategy": "dev_first_promotion",
            "databricks": {"workspace_urls": {"dev": "https://adb-dev.example.net"}},
        }
    )
    assert config.is_simulate_mode() is True


def test_legacy_local_mode_maps_to_connected() -> None:
    """Legacy local_mode flag should remain backward compatible."""
    config = AppConfig.model_validate(
        {
            "local_mode": False,
            "databricks": {"workspace_urls": {"dev": "https://adb-dev.example.net"}},
        }
    )
    assert config.integration_mode == "connected"
    assert config.is_simulate_mode() is False
