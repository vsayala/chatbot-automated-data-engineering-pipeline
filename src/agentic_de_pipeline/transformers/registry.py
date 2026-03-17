"""Registry and execution manager for remediation transformers."""

from __future__ import annotations

from dataclasses import dataclass
from logging import Logger

from agentic_de_pipeline.transformers.base import RemediationContext, RemediationTransformer, TransformerResult
from agentic_de_pipeline.transformers.databricks_notebook import DatabricksNotebookTransformer
from agentic_de_pipeline.transformers.python_etl import PythonETLTransformer
from agentic_de_pipeline.transformers.sql import SQLTransformer


@dataclass(slots=True)
class TransformerExecutionReport:
    """Aggregated report from executing remediation transformers."""

    applied_results: list[TransformerResult]

    @property
    def changed_files(self) -> list[str]:
        """Flatten all changed files from applied transformer results."""
        files: list[str] = []
        for result in self.applied_results:
            files.extend(result.changed_files)
        return files

    @property
    def was_changed(self) -> bool:
        """Return True if at least one transformer changed a file."""
        return bool(self.changed_files)

    def to_summary(self) -> str:
        """Build concise transformer trail summary."""
        if not self.applied_results:
            return "no transformer plugin changed repository files"
        entries = [
            f"{result.plugin_name}:{len(result.changed_files)} file(s)"
            for result in self.applied_results
        ]
        return ", ".join(entries)


class TransformerRegistry:
    """Orchestrates plugin selection and execution for remediation edits."""

    def __init__(self, enabled_plugins: list[str], logger: Logger) -> None:
        self.logger = logger
        ordered_plugins: list[RemediationTransformer] = [
            DatabricksNotebookTransformer(),
            SQLTransformer(),
            PythonETLTransformer(),
        ]
        enabled_set = {name.strip().lower() for name in enabled_plugins}
        self._plugins = [plugin for plugin in ordered_plugins if plugin.plugin_name in enabled_set]

    def apply(self, context: RemediationContext) -> TransformerExecutionReport:
        """Execute matching transformers and return aggregated change report."""
        applied_results: list[TransformerResult] = []
        for plugin in self._plugins:
            if not plugin.can_transform(context):
                continue
            result = plugin.transform(context)
            if not result.changed:
                self.logger.info(
                    "transformer_noop plugin=%s work_item_id=%s",
                    plugin.plugin_name,
                    context.work_item.id,
                )
                continue
            self.logger.info(
                "transformer_applied plugin=%s changed_files=%s work_item_id=%s",
                plugin.plugin_name,
                len(result.changed_files),
                context.work_item.id,
            )
            applied_results.append(result)
        return TransformerExecutionReport(applied_results=applied_results)
