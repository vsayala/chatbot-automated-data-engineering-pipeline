"""SQL remediation transformer."""

from __future__ import annotations

from pathlib import Path

from agentic_de_pipeline.transformers.base import RemediationContext, RemediationTransformer, TransformerResult


class SQLTransformer(RemediationTransformer):
    """Patch SQL assets when pipeline errors indicate missing catalog/schema objects."""

    plugin_name = "sql"

    _FAILURE_HINTS = ("table", "view", "schema", "catalog", "not found", "does not exist")

    def can_transform(self, context: RemediationContext) -> bool:
        failure_context = context.failure_context.lower()
        if not any(token in failure_context for token in self._FAILURE_HINTS):
            return False
        return True

    def transform(self, context: RemediationContext) -> TransformerResult:
        block = self._build_bootstrap_block(context)
        changed_files: list[str] = []
        candidates = self._candidate_files(context.repo_path, context)
        for sql_path in candidates[:5]:
            try:
                content = sql_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if "CREATE SCHEMA IF NOT EXISTS" in content and context.plan.target_schema in content:
                continue
            sql_path.write_text(block + content, encoding="utf-8")
            changed_files.append(str(sql_path))
            break

        if not changed_files:
            generated_path = context.repo_path / "sql" / f"remediation_bootstrap_wi_{context.work_item.id}.sql"
            generated_path.parent.mkdir(parents=True, exist_ok=True)
            generated_path.write_text(block, encoding="utf-8")
            changed_files.append(str(generated_path))

        summary = "Added SQL bootstrap statements for catalog/schema existence."
        return TransformerResult(plugin_name=self.plugin_name, changed_files=changed_files, summary=summary)

    def _candidate_files(self, repo_path: Path, context: RemediationContext) -> list[Path]:
        sql_files = sorted(repo_path.glob("**/*.sql"))
        if not sql_files:
            return []
        table_name = context.plan.target_table.lower()
        schema_name = context.plan.target_schema.lower()
        preferred: list[Path] = []
        for file_path in sql_files:
            try:
                body = file_path.read_text(encoding="utf-8").lower()
            except UnicodeDecodeError:
                continue
            if table_name in body or schema_name in body:
                preferred.append(file_path)
        return preferred or sql_files

    def _build_bootstrap_block(self, context: RemediationContext) -> str:
        catalog = context.plan.target_catalog
        schema = context.plan.target_schema
        return (
            "-- Added by remediation plugin to prevent missing namespace failures.\n"
            f"CREATE CATALOG IF NOT EXISTS {catalog};\n"
            f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema};\n\n"
        )
