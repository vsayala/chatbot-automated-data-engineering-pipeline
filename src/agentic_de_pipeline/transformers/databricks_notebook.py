"""Databricks notebook remediation transformer."""

from __future__ import annotations

from pathlib import Path
import re

from agentic_de_pipeline.transformers.base import RemediationContext, RemediationTransformer, TransformerResult


class DatabricksNotebookTransformer(RemediationTransformer):
    """Patch Databricks notebook-style Python files for common Delta issues."""

    plugin_name = "databricks_notebook"

    _FAILURE_HINTS = ("analysisexception", "schema mismatch", "delta", "databricks", "notebook")
    _CONF_LINE = 'spark.conf.set("spark.databricks.delta.schema.autoMerge.enabled", "true")'
    _SPARK_BOOTSTRAP = [
        "try:",
        "    spark",
        "except NameError:",
        "    from pyspark.sql import SparkSession",
        "    spark = SparkSession.builder.getOrCreate()",
    ]

    def can_transform(self, context: RemediationContext) -> bool:
        failure_context = context.failure_context.lower()
        if not any(token in failure_context for token in self._FAILURE_HINTS):
            return False
        return any(self._candidate_files(context.repo_path))

    def transform(self, context: RemediationContext) -> TransformerResult:
        changed_files: list[str] = []
        for notebook_path in self._candidate_files(context.repo_path):
            try:
                content = notebook_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if self._CONF_LINE in content:
                continue
            updated = self._inject_auto_merge_config(content)
            if updated == content:
                continue
            notebook_path.write_text(updated, encoding="utf-8")
            changed_files.append(str(notebook_path))
        summary = "Enabled Delta auto-merge in Databricks notebook code paths."
        return TransformerResult(plugin_name=self.plugin_name, changed_files=changed_files, summary=summary)

    def _candidate_files(self, repo_path: Path) -> list[Path]:
        files: list[Path] = []
        files.extend(sorted(repo_path.glob("notebooks/**/*.py")))
        files.extend(sorted(repo_path.glob("**/*notebook*.py")))
        deduped: list[Path] = []
        seen: set[Path] = set()
        for file_path in files:
            resolved = file_path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            deduped.append(file_path)
        return deduped[:10]

    def _inject_auto_merge_config(self, content: str) -> str:
        lines = content.splitlines()

        # Preserve shebang and PEP 263 encoding cookie at the very top of the file.
        header_end = 0
        if lines and lines[0].startswith("#!"):
            header_end = 1
        if len(lines) > header_end:
            # PEP 263: encoding declaration must be in line 1 or 2.
            encoding_pattern = r"^[ \t]*#.*coding[:=][ \t]*[-\w.]+"
            if re.match(encoding_pattern, lines[header_end]):
                header_end += 1

        insert_at = header_end
        for index in range(header_end, len(lines)):
            line = lines[index]
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                insert_at = index + 1
                continue
            if stripped == "":
                continue
            break

        snippet = [
            "",
            "# Added by remediation plugin for Delta schema evolution compatibility.",
            *self._SPARK_BOOTSTRAP,
            self._CONF_LINE,
        ]
        if lines and lines[-1].strip():
            snippet.append("")
        return "\n".join(lines[:insert_at] + snippet + lines[insert_at:]) + ("\n" if content.endswith("\n") else "")
