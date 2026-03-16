"""Unit tests for Azure DevOps priority intake behavior."""

from __future__ import annotations

import json
from pathlib import Path

from agentic_de_pipeline.adapters.azure_devops import AzureDevOpsClient


def test_mock_work_items_are_sorted_by_priority(test_config, tmp_path: Path) -> None:
    """Adapter should return work items ordered by ascending priority."""
    mock_path = tmp_path / "work_items.json"
    mock_path.write_text(
        json.dumps(
            [
                {
                    "id": 1,
                    "title": "Low priority",
                    "description": "",
                    "item_type": "User Story",
                    "priority": 3,
                    "tags": ["repo:repo-c"],
                },
                {
                    "id": 2,
                    "title": "High priority",
                    "description": "",
                    "item_type": "Bug",
                    "priority": 1,
                    "tags": ["repo:repo-a"],
                },
                {
                    "id": 3,
                    "title": "Medium priority",
                    "description": "",
                    "item_type": "Product Backlog Item",
                    "priority": 2,
                    "tags": ["repo:repo-b"],
                },
            ]
        ),
        encoding="utf-8",
    )

    test_config.azure_devops.mock_data_path = str(mock_path)
    client = AzureDevOpsClient(test_config)

    items = client.fetch_open_work_items(limit=3)

    assert [item.id for item in items] == [2, 3, 1]
    assert items[0].repo_name == "repo-a"
