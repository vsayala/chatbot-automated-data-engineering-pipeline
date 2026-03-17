"""Unit tests for clarification and DevOps discussion recording."""

from __future__ import annotations

from agentic_de_pipeline.adapters.azure_devops import AzureDevOpsClient
from agentic_de_pipeline.approvals.human_loop import HumanApprovalService


def test_clarification_request_auto_mode_returns_answers(test_config) -> None:
    """Auto mode should return answered clarification payload."""
    service = HumanApprovalService(test_config.approvals, test_config.logging.log_dir)

    clarification = service.request_clarification(
        work_item_id=123,
        work_item_title="Need missing details",
        questions=["Provide catalog.schema.table", "Append or overwrite?"],
    )

    assert clarification.status == "answered"
    assert len(clarification.answers) == 2


def test_simulate_mode_can_record_work_item_discussion_comment(test_config) -> None:
    """Simulate mode comment update should not fail and return local marker."""
    client = AzureDevOpsClient(test_config)
    comment_id = client.add_work_item_discussion_comment(123, "Test clarification note")

    assert comment_id == "local-comment-saved"
