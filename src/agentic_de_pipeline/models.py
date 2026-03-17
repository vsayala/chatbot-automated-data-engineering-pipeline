"""Core domain models for the agentic pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4


class WorkItemType(str, Enum):
    """Supported Azure DevOps work item categories."""

    PRODUCT_BACKLOG_ITEM = "Product Backlog Item"
    BUG = "Bug"
    USER_STORY = "User Story"


class ApprovalStatus(str, Enum):
    """Human approval status values."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"


@dataclass(slots=True)
class WorkItem:
    """Represents a normalized work item from Azure DevOps."""

    id: int
    title: str
    description: str
    item_type: WorkItemType
    tags: list[str] = field(default_factory=list)
    acceptance_criteria: str = ""
    priority: int = 9999
    repo_name: str | None = None
    state: str = "Active"


@dataclass(slots=True)
class RequirementPlan:
    """Structured implementation plan produced by the requirement agent."""

    work_item_id: int
    summary: str
    source_types: list[str]
    ingestion_mode: str
    target_layer: str
    target_catalog: str
    target_schema: str
    target_table: str
    target_repo: str
    branch_name: str
    notebook_tasks: list[str]
    risk_notes: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    clarification_questions: list[str] = field(default_factory=list)
    clarification_answers: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class PipelineRunResult:
    """Represents an Azure Pipeline execution result."""

    run_id: str
    pipeline_name: str
    environment: str
    status: str
    started_at: datetime
    finished_at: datetime
    dashboard_url: str
    logs_url: str = ""


@dataclass(slots=True)
class StageResult:
    """Outcome for an environment stage (dev/qe/stg/prod)."""

    environment: str
    status: str
    details: str
    started_at: datetime
    finished_at: datetime


@dataclass(slots=True)
class ApprovalRequest:
    """Pending or completed human-in-loop approval request."""

    stage: str
    summary: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    approver: str | None = None
    comment: str | None = None
    request_id: str = field(default_factory=lambda: f"apr-{uuid4()}")
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_dict(self) -> dict[str, Any]:
        """Serialize approval request for API/file storage."""
        return {
            "request_id": self.request_id,
            "stage": self.stage,
            "summary": self.summary,
            "status": self.status.value,
            "approver": self.approver,
            "comment": self.comment,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(slots=True)
class WorkflowRunSummary:
    """Aggregated output from one orchestration cycle."""

    work_item_id: int
    work_item_title: str
    overall_status: str
    repo_workflow_status: str
    repo_workflow_details: str
    stage_results: list[StageResult]
    clarification_status: str = "not_required"
    clarification_details: str = ""
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class ClarificationRequest:
    """Pending or completed clarification request for incomplete requirements."""

    work_item_id: int
    work_item_title: str
    questions: list[str]
    status: str = "pending"
    answers: dict[str, str] = field(default_factory=dict)
    requester: str = "agent"
    request_id: str = field(default_factory=lambda: f"clr-{uuid4()}")
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_dict(self) -> dict[str, Any]:
        """Serialize clarification request for API/file storage."""
        return {
            "request_id": self.request_id,
            "work_item_id": self.work_item_id,
            "work_item_title": self.work_item_title,
            "questions": self.questions,
            "status": self.status,
            "answers": self.answers,
            "requester": self.requester,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(slots=True)
class LearningRecord:
    """Model for persistent learning memory entries."""

    work_item_id: int
    title: str
    status: str
    target_table: str
    source_types: list[str]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
