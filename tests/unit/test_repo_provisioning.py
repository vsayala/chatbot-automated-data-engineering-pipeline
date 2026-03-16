"""Unit tests for repository provisioning edge cases."""

from __future__ import annotations

from agentic_de_pipeline.adapters.azure_repos import AzureReposClient


def test_dry_run_can_provision_new_repository(test_config) -> None:
    """Dry run should simulate repository creation for missing target repo."""
    client = AzureReposClient(test_config)

    ready, details = client.ensure_repository("new-team-data-repo")

    assert ready is True
    assert details.startswith("dry-run-created-repo:")
