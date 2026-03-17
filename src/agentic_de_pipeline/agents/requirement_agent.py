"""Requirement interpretation agent for DevOps work items."""

from __future__ import annotations

import re

from agentic_de_pipeline.logging_utils import get_module_logger
from agentic_de_pipeline.models import RequirementPlan, WorkItem
from agentic_de_pipeline.services.mcp_router import MCPRouter
from agentic_de_pipeline.services.prompt_engine import PromptEngine
from agentic_de_pipeline.state_store import LearningStore
from agentic_de_pipeline.utils.retry import RetryPolicy


class RequirementAgent:
    """Converts work items into implementation plans."""

    def __init__(
        self,
        log_dir: str,
        learning_store: LearningStore,
        prompt_engine: PromptEngine,
        mcp_router: MCPRouter,
        default_repo_name: str,
        branch_prefix: str,
        retry_policy: RetryPolicy,
        fail_on_mcp_error: bool,
    ) -> None:
        self.learning_store = learning_store
        self.prompt_engine = prompt_engine
        self.mcp_router = mcp_router
        self.default_repo_name = default_repo_name
        self.branch_prefix = branch_prefix
        self.retry_policy = retry_policy
        self.fail_on_mcp_error = fail_on_mcp_error
        self.logger = get_module_logger(
            module_name="agentic_de_pipeline.requirement_agent",
            log_dir=log_dir,
            file_name="requirement_agent.log",
        )

    def build_plan(self, work_item: WorkItem) -> RequirementPlan:
        """Generate a normalized plan from requirement text."""
        text_blob = f"{work_item.title} {work_item.description} {work_item.acceptance_criteria}".lower()

        source_types, sources_explicit = self._extract_source_types(text_blob)
        ingestion_mode, ingestion_explicit = self._extract_ingestion_mode(text_blob)
        target_catalog, target_schema, target_table, table_explicit = self._extract_target_table(work_item)
        target_repo = work_item.repo_name or self.default_repo_name
        branch_name = self._build_branch_name(work_item)

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

        mcp_snapshot = self.mcp_router.status_snapshot()
        mcp_enrichment: dict = {}
        if self.mcp_router.is_enabled():
            try:
                preferred_server = (
                    "azure_devops_mcp"
                    if "azure_devops_mcp" in self.mcp_router.config.servers
                    else next(iter(self.mcp_router.config.servers), "")
                )
                if not preferred_server:
                    raise RuntimeError("MCP enabled but no servers are configured.")
                mcp_enrichment = self.mcp_router.invoke_action(
                    server_name=preferred_server,
                    action="enrich_work_item",
                    payload={
                        "id": work_item.id,
                        "title": work_item.title,
                        "description": work_item.description,
                        "acceptance_criteria": work_item.acceptance_criteria,
                    },
                    retry_policy=self.retry_policy,
                )
                source_types = mcp_enrichment.get("source_types", source_types)
                ingestion_mode = mcp_enrichment.get("ingestion_mode", ingestion_mode)
            except Exception as exc:  # pylint: disable=broad-except
                self.logger.warning("mcp_enrichment_failed work_item_id=%s error=%s", work_item.id, exc)
                if self.fail_on_mcp_error:
                    raise
        summary_prompt = self.prompt_engine.render(
            "requirement_summary",
            {
                "title": work_item.title,
                "description": work_item.description,
                "acceptance_criteria": work_item.acceptance_criteria,
                "target_repo": target_repo,
                "priority": work_item.priority,
                "mcp_status": mcp_snapshot,
                "mcp_enrichment": mcp_enrichment,
                "fallback": f"Implement {work_item.title}",
            },
        )
        summary = self.prompt_engine.generate_text(summary_prompt)
        clarification_questions = self._build_clarification_questions(
            work_item=work_item,
            table_explicit=table_explicit,
            sources_explicit=sources_explicit,
            ingestion_explicit=ingestion_explicit,
        )

        plan = RequirementPlan(
            work_item_id=work_item.id,
            summary=summary,
            source_types=source_types,
            ingestion_mode=ingestion_mode,
            target_layer="bronze",
            target_catalog=target_catalog,
            target_schema=target_schema,
            target_table=target_table,
            target_repo=target_repo,
            branch_name=branch_name,
            notebook_tasks=notebook_tasks,
            risk_notes=self._collect_risk_notes(source_types, ingestion_mode),
            needs_clarification=bool(clarification_questions),
            clarification_questions=clarification_questions,
        )
        self.logger.info(
            "requirement_plan_created work_item_id=%s priority=%s repo=%s target=%s.%s.%s mode=%s",
            plan.work_item_id,
            work_item.priority,
            plan.target_repo,
            plan.target_catalog,
            plan.target_schema,
            plan.target_table,
            plan.ingestion_mode,
        )
        return plan

    def apply_clarification_answers(self, plan: RequirementPlan, answers: dict[str, str]) -> RequirementPlan:
        """Update a plan with clarification answers from human-in-loop."""
        normalized_answers = {key: value.strip() for key, value in answers.items() if value.strip()}
        answer_blob = " ".join(normalized_answers.values()).lower()

        # Update table details if human provided explicit catalog.schema.table.
        table_match = re.search(r"([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)", answer_blob)
        if table_match:
            plan.target_catalog = table_match.group(1).lower()
            plan.target_schema = table_match.group(2).lower()
            plan.target_table = table_match.group(3).lower()

        # Update ingestion mode from answer text.
        if "overwrite" in answer_blob:
            plan.ingestion_mode = "overwrite"
        elif "append" in answer_blob:
            plan.ingestion_mode = "append"

        # Update source type hints.
        updated_sources: list[str] = []
        if "jdbc" in answer_blob or "edw" in answer_blob:
            updated_sources.append("jdbc")
        if "flat file" in answer_blob or "volume" in answer_blob or "csv" in answer_blob:
            updated_sources.append("flat_file")
        if updated_sources:
            plan.source_types = sorted(set(updated_sources))

        # Update target repo if provided.
        repo_from_answer = self._extract_repo_from_answers(normalized_answers)
        if repo_from_answer:
            plan.target_repo = repo_from_answer

        plan.clarification_answers.update(normalized_answers)
        remaining = [question for question in plan.clarification_questions if not self._has_answer_for(question, normalized_answers)]
        plan.clarification_questions = remaining
        plan.needs_clarification = bool(remaining)
        return plan

    def _extract_source_types(self, text_blob: str) -> tuple[list[str], bool]:
        sources = []
        explicit = False
        if "jdbc" in text_blob or "edw" in text_blob:
            sources.append("jdbc")
            explicit = True
        if "flat file" in text_blob or "volume" in text_blob or "csv" in text_blob:
            sources.append("flat_file")
            explicit = True
        if not sources:
            sources.append("unknown")
        return sources, explicit

    @staticmethod
    def _extract_ingestion_mode(text_blob: str) -> tuple[str, bool]:
        if "overwrite" in text_blob:
            return "overwrite", True
        if "append" in text_blob:
            return "append", True
        return "append", False

    @staticmethod
    def _extract_target_table(work_item: WorkItem) -> tuple[str, str, str, bool]:
        catalog = "main"
        schema = "bronze"
        table = f"wi_{work_item.id}_table"

        combined_text = f"{work_item.title} {work_item.description} {work_item.acceptance_criteria}"
        matches = re.findall(r"([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)", combined_text)
        if matches:
            catalog, schema, table = matches[0]
            return catalog.lower(), schema.lower(), table.lower(), True
        return catalog.lower(), schema.lower(), table.lower(), False

    def _build_branch_name(self, work_item: WorkItem) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", work_item.title.lower()).strip("-")
        slug = slug[:35] if slug else "work-item"
        return f"{self.branch_prefix}{work_item.id}-{slug}"

    @staticmethod
    def _collect_risk_notes(source_types: list[str], ingestion_mode: str) -> list[str]:
        notes: list[str] = []
        if "jdbc" in source_types:
            notes.append("Validate JDBC credentials and source-side throttling.")
        if ingestion_mode == "overwrite":
            notes.append("Ensure overwrite strategy is approved for target table.")
        return notes

    @staticmethod
    def _build_clarification_questions(
        work_item: WorkItem,
        table_explicit: bool,
        sources_explicit: bool,
        ingestion_explicit: bool,
    ) -> list[str]:
        questions: list[str] = []
        if not table_explicit:
            questions.append(
                "Please provide the exact Unity Catalog target table as <catalog>.<schema>.<table>."
            )
        if not sources_explicit:
            questions.append(
                "What is the ingestion source type (jdbc/flat file/volume/other) and connection details?"
            )
        if not ingestion_explicit:
            questions.append("Should ingestion mode be append or overwrite?")
        if not work_item.repo_name:
            questions.append(
                "Which repository should be used? If new, provide repository name and confirm creation."
            )
        if not work_item.acceptance_criteria.strip():
            questions.append("Please provide acceptance criteria and data quality expectations.")
        return questions

    @staticmethod
    def _has_answer_for(question: str, answers: dict[str, str]) -> bool:
        """Check if answers include explicit response for question semantics."""
        question_key = question.lower()
        for key, value in answers.items():
            candidate = f"{key.lower()} {value.lower()}"
            if "catalog" in question_key and "." in value:
                return True
            if "source type" in question_key and any(term in candidate for term in ("jdbc", "flat", "volume", "csv")):
                return True
            if "append or overwrite" in question_key and any(term in candidate for term in ("append", "overwrite")):
                return True
            if "repository" in question_key and value.strip():
                return True
            if "acceptance criteria" in question_key and value.strip():
                return True
        return False

    @staticmethod
    def _extract_repo_from_answers(answers: dict[str, str]) -> str | None:
        for question, answer in answers.items():
            if "repository" in question.lower():
                cleaned = answer.strip().replace("repo:", "")
                cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "-", cleaned)
                return cleaned.strip("-") or None
        return None
