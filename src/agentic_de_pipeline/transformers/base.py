"""Base models and interfaces for remediation code transformers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from agentic_de_pipeline.models import RequirementPlan, WorkItem


@dataclass(slots=True)
class RemediationContext:
    """Context passed into remediation transformers."""

    work_item: WorkItem
    plan: RequirementPlan
    environment: str
    failure_context: str
    suggestion: str
    attempt: int
    repo_path: Path


@dataclass(slots=True)
class TransformerResult:
    """Outcome of a transformer execution."""

    plugin_name: str
    changed_files: list[str] = field(default_factory=list)
    summary: str = ""

    @property
    def changed(self) -> bool:
        """Return True when any code file was updated by this plugin."""
        return bool(self.changed_files)


class RemediationTransformer(ABC):
    """Abstract base for repo-specific remediation transformers."""

    plugin_name: str

    @abstractmethod
    def can_transform(self, context: RemediationContext) -> bool:
        """Return True when this transformer should run."""

    @abstractmethod
    def transform(self, context: RemediationContext) -> TransformerResult:
        """Apply remediation edits and return changed files."""
