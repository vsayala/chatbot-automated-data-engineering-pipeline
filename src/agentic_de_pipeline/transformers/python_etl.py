"""Python ETL remediation transformer."""

from __future__ import annotations

import re
from pathlib import Path

from agentic_de_pipeline.transformers.base import RemediationContext, RemediationTransformer, TransformerResult


class PythonETLTransformer(RemediationTransformer):
    """Patch Python ETL writers for schema-evolution friendly writes."""

    plugin_name = "python_etl"

    _FAILURE_HINTS = ("schema mismatch", "analysisexception", "cannot resolve", "column", "delta")
    _MODE_PATTERN = re.compile(r'(\.mode\(\s*"(?:append|overwrite)"\s*\)\s*)(?!\.\s*option\(\s*"mergeSchema")')

    def can_transform(self, context: RemediationContext) -> bool:
        failure_context = context.failure_context.lower()
        if not any(token in failure_context for token in self._FAILURE_HINTS):
            return False
        return any(self._candidate_files(context.repo_path))

    def transform(self, context: RemediationContext) -> TransformerResult:
        changed_files: list[str] = []
        for file_path in self._candidate_files(context.repo_path):
            try:
                content = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            updated, changed = self._add_merge_schema_option(content)
            if not changed:
                continue
            file_path.write_text(updated, encoding="utf-8")
            changed_files.append(str(file_path))
            if len(changed_files) >= 3:
                break
        summary = "Added mergeSchema write option to Python ETL Delta writes."
        return TransformerResult(plugin_name=self.plugin_name, changed_files=changed_files, summary=summary)

    def _candidate_files(self, repo_path: Path) -> list[Path]:
        candidates = sorted(repo_path.glob("**/*.py"))
        filtered: list[Path] = []
        for path in candidates:
            parts = {part.lower() for part in path.parts}
            if "tests" in parts or "generated_changes" in parts or "transformers" in parts:
                continue
            if {"etl", "pipelines", "jobs", "notebooks"} & parts:
                filtered.append(path)
        return filtered[:30]

    def _add_merge_schema_option(self, content: str) -> tuple[str, bool]:
        replacement = r'\1.option("mergeSchema", "true")'
        updated, count = self._MODE_PATTERN.subn(replacement, content, count=1)
        return updated, count > 0
