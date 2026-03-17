"""Unit tests for repo-specific remediation transformer plugins."""

from __future__ import annotations

import logging
from pathlib import Path

from agentic_de_pipeline.models import RequirementPlan, WorkItem, WorkItemType
from agentic_de_pipeline.transformers import (
    DatabricksNotebookTransformer,
    PythonETLTransformer,
    RemediationContext,
    SQLTransformer,
    TransformerRegistry,
)


def _build_context(repo_path: Path, failure_context: str) -> RemediationContext:
    work_item = WorkItem(
        id=901,
        title="Fix ingestion schema mismatch",
        description="pipeline failed",
        item_type=WorkItemType.BUG,
        priority=1,
        repo_name="test-repo",
    )
    plan = RequirementPlan(
        work_item_id=work_item.id,
        summary="Fix bronze ingestion",
        source_types=["jdbc"],
        ingestion_mode="append",
        target_layer="bronze",
        target_catalog="main",
        target_schema="bronze",
        target_table="customers",
        target_repo="test-repo",
        branch_name="feature/pbi-901-fix",
        notebook_tasks=["ingest_customers"],
    )
    return RemediationContext(
        work_item=work_item,
        plan=plan,
        environment="qe",
        failure_context=failure_context,
        suggestion="Apply targeted schema remediation",
        attempt=1,
        repo_path=repo_path,
    )


def test_databricks_notebook_transformer_injects_auto_merge(tmp_path: Path) -> None:
    """Notebook plugin should inject Delta auto-merge config once."""
    notebook = tmp_path / "notebooks" / "ingest.py"
    notebook.parent.mkdir(parents=True, exist_ok=True)
    notebook.write_text('import json\n\ndf.write.format("delta").mode("append").saveAsTable("main.bronze.customers")\n', encoding="utf-8")

    transformer = DatabricksNotebookTransformer()
    context = _build_context(tmp_path, "AnalysisException: schema mismatch in Databricks notebook")
    result = transformer.transform(context)

    assert result.changed_files == [str(notebook)]
    updated = notebook.read_text(encoding="utf-8")
    assert 'spark.conf.set("spark.databricks.delta.schema.autoMerge.enabled", "true")' in updated


def test_sql_transformer_prepends_bootstrap_block(tmp_path: Path) -> None:
    """SQL plugin should prepend CREATE CATALOG/SCHEMA statements."""
    sql_file = tmp_path / "sql" / "create_customers.sql"
    sql_file.parent.mkdir(parents=True, exist_ok=True)
    sql_file.write_text("CREATE TABLE main.bronze.customers (id INT);\n", encoding="utf-8")

    transformer = SQLTransformer()
    context = _build_context(tmp_path, "Table not found during deployment")
    result = transformer.transform(context)

    assert result.changed_files == [str(sql_file)]
    updated = sql_file.read_text(encoding="utf-8")
    assert "CREATE CATALOG IF NOT EXISTS main;" in updated
    assert "CREATE SCHEMA IF NOT EXISTS main.bronze;" in updated


def test_python_etl_transformer_adds_merge_schema_option(tmp_path: Path) -> None:
    """Python ETL plugin should patch Delta write chain with mergeSchema option."""
    etl_file = tmp_path / "etl" / "ingest.py"
    etl_file.parent.mkdir(parents=True, exist_ok=True)
    etl_file.write_text(
        "\n".join(
            [
                "def run(df):",
                "    (",
                "        df.write.format(\"delta\")",
                "        .mode(\"append\")",
                "        .saveAsTable(\"main.bronze.customers\")",
                "    )",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    transformer = PythonETLTransformer()
    context = _build_context(tmp_path, "Schema mismatch while writing delta table")
    result = transformer.transform(context)

    assert result.changed_files == [str(etl_file)]
    updated = etl_file.read_text(encoding="utf-8")
    assert '.mode("append").option("mergeSchema", "true")' in updated


def test_transformer_registry_applies_enabled_plugins(tmp_path: Path) -> None:
    """Registry should apply only configured plugin set."""
    notebook = tmp_path / "notebooks" / "ingest.py"
    notebook.parent.mkdir(parents=True, exist_ok=True)
    notebook.write_text("spark.sql('SELECT 1')\n", encoding="utf-8")

    context = _build_context(tmp_path, "Databricks notebook failure in delta job")
    registry = TransformerRegistry(
        enabled_plugins=["databricks_notebook"],
        logger=logging.getLogger("test"),
    )
    report = registry.apply(context)

    assert report.was_changed is True
    assert len(report.applied_results) == 1
    assert report.applied_results[0].plugin_name == "databricks_notebook"
