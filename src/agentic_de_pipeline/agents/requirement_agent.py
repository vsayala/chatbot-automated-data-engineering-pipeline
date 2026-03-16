"""Requirement interpretation agent for DevOps work items."""

from __future__ import annotations

import re

from agentic_de_pipeline.logging_utils import get_module_logger
from agentic_de_pipeline.models import RequirementPlan, WorkItem
from agentic_de_pipeline.state_store import LearningStore


class RequirementAgent:
    """Converts work items into implementation plans."""

    def __init__(self, log_dir: str, learning_store: LearningStore) -> None:
        self.learning_store = learning_store
        self.logger = get_module_logger(
            module_name="agentic_de_pipeline.requirement_agent",
            log_dir=log_dir,
            file_name="requirement_agent.log",
        )

    def build_plan(self, work_item: WorkItem) -> RequirementPlan:
        """Generate a normalized plan from requirement text."""
        text_blob = f"{work_item.title} {work_item.description} {work_item.acceptance_criteria}".lower()

        source_types = self._extract_source_types(text_blob)
        ingestion_mode = self._extract_ingestion_mode(text_blob)
        target_catalog, target_schema, target_table = self._extract_target_table(work_item)

        ranked_history = self.learning_store.suggest_source_priority()
        if ranked_history:
            source_types = sorted(
                source_types,
                key=lambda source: ranked_history.index(source)
                if source in ranked_history
                else len(ranked_history),
            )

        notebook_tasks = [
            "create_unity_catalog_table",
            "run_ingestion_notebook",
            "run_data_quality_checks",
        ]

        plan = RequirementPlan(
            work_item_id=work_item.id,
            summary=f"Implement {work_item.title}",
            source_types=source_types,
            ingestion_mode=ingestion_mode,
            target_layer="bronze",
            target_catalog=target_catalog,
            target_schema=target_schema,
            target_table=target_table,
            notebook_tasks=notebook_tasks,
            risk_notes=self._collect_risk_notes(source_types, ingestion_mode),
        )
        self.logger.info(
            "requirement_plan_created work_item_id=%s target=%s.%s.%s mode=%s",
            plan.work_item_id,
            plan.target_catalog,
            plan.target_schema,
            plan.target_table,
            plan.ingestion_mode,
        )
        return plan

    def _extract_source_types(self, text_blob: str) -> list[str]:
        sources = []
        if "jdbc" in text_blob or "edw" in text_blob:
            sources.append("jdbc")
        if "flat file" in text_blob or "volume" in text_blob or "csv" in text_blob:
            sources.append("flat_file")
        if not sources:
            sources.append("unknown")
        return sources

    @staticmethod
    def _extract_ingestion_mode(text_blob: str) -> str:
        if "overwrite" in text_blob:
            return "overwrite"
        if "append" in text_blob:
            return "append"
        return "append"

    @staticmethod
    def _extract_target_table(work_item: WorkItem) -> tuple[str, str, str]:
        catalog = "main"
        schema = "bronze"
        table = f"wi_{work_item.id}_table"

        matches = re.findall(r"([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)", work_item.title)
        if matches:
            catalog, schema, table = matches[0]
        return catalog.lower(), schema.lower(), table.lower()

    @staticmethod
    def _collect_risk_notes(source_types: list[str], ingestion_mode: str) -> list[str]:
        notes: list[str] = []
        if "jdbc" in source_types:
            notes.append("Validate JDBC credentials and source-side throttling.")
        if ingestion_mode == "overwrite":
            notes.append("Ensure overwrite strategy is approved for target table.")
        return notes
