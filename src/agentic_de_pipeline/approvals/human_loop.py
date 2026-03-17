"""Human-in-the-loop approval workflow management."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from agentic_de_pipeline.config import ApprovalConfig
from agentic_de_pipeline.logging_utils import get_module_logger
from agentic_de_pipeline.models import ApprovalRequest, ApprovalStatus, ClarificationRequest
from agentic_de_pipeline.state_store import JsonStateStore


class HumanApprovalService:
    """Creates and resolves manual approvals for workflow stages."""

    def __init__(self, config: ApprovalConfig, log_dir: str) -> None:
        self.config = config
        self.store = JsonStateStore(config.state_file)
        self.logger = get_module_logger(
            module_name="agentic_de_pipeline.human_approval",
            log_dir=log_dir,
            file_name="approvals.log",
        )
        self._bootstrap()

    def _bootstrap(self) -> None:
        data = self.store.read()
        if "requests" not in data:
            data["requests"] = []
        if "clarifications" not in data:
            data["clarifications"] = []
        if "last_answers" not in data:
            data["last_answers"] = {}
        if "last_request_id" not in data:
            data["last_request_id"] = ""
        self.store.write(data)

    def list_pending(self) -> list[dict]:
        """List pending approvals for chatbot/operator UI."""
        data = self.store.read()
        return [row for row in data.get("requests", []) if row.get("status") == ApprovalStatus.PENDING.value]

    def list_pending_with_guidance(self) -> list[dict]:
        """List pending approvals enriched with stage-aware suggestions."""
        pending = self.list_pending()
        output: list[dict] = []
        for row in pending:
            guidance = self.get_stage_guidance(str(row.get("stage", "")))
            output.append({**row, "guidance": guidance})
        return output

    def get_stage_guidance(self, stage: str) -> dict:
        """Get actionable checklist for given stage."""
        return self._build_stage_guidance(stage)

    def list_pending_clarifications(self) -> list[dict]:
        """List pending clarification requests."""
        data = self.store.read()
        return [row for row in data.get("clarifications", []) if row.get("status") == "pending"]

    def submit_clarification_answers(
        self,
        request_id: str,
        responder: str,
        answers: dict[str, str],
    ) -> bool:
        """Submit clarification answers from human-in-loop."""
        data = self.store.read()
        updated = False
        for row in data.get("clarifications", []):
            if row.get("request_id") == request_id:
                row["answers"] = answers
                row["status"] = "answered"
                row["responder"] = responder
                row["updated_at"] = datetime.now(UTC).isoformat()
                updated = True
                break
        if updated:
            data["last_answers"] = answers
            data["last_request_id"] = request_id
            self.store.write(data)
            self.logger.info("clarification_answers_saved request_id=%s responder=%s", request_id, responder)
        return updated

    def update_clarification_status(self, request_id: str, status: str, responder: str, answers: dict[str, str] | None = None) -> bool:
        """Update clarification status directly without forcing answered state."""
        data = self.store.read()
        updated = False
        for row in data.get("clarifications", []):
            if row.get("request_id") == request_id:
                row["status"] = status
                row["responder"] = responder
                if answers is not None:
                    row["answers"] = answers
                    data["last_answers"] = answers
                data["last_request_id"] = request_id
                row["updated_at"] = datetime.now(UTC).isoformat()
                updated = True
                break
        if updated:
            self.store.write(data)
        return updated

    def request_clarification(
        self,
        work_item_id: int,
        work_item_title: str,
        questions: list[str],
    ) -> ClarificationRequest:
        """Create and resolve clarification request for missing work-item details."""
        clarification = ClarificationRequest(
            work_item_id=work_item_id,
            work_item_title=work_item_title,
            questions=questions,
        )
        data = self.store.read()
        clarifications = data.setdefault("clarifications", [])
        clarifications.append(clarification.as_dict())
        self.store.write(data)
        self.logger.info("clarification_requested work_item_id=%s request_id=%s", work_item_id, clarification.request_id)

        mode = self.config.mode.lower().strip()
        if mode == "console":
            return self._resolve_clarification_console(clarification.request_id)
        if mode == "api":
            return self._resolve_clarification_api_wait(clarification.request_id)
        if mode == "auto":
            auto_answers = {question: "auto-default" for question in questions}
            self.submit_clarification_answers(
                request_id=clarification.request_id,
                responder="auto-mode",
                answers=auto_answers,
            )
            return self.get_clarification(clarification.request_id)
        raise ValueError(f"Unsupported clarification mode: {self.config.mode}")

    def get_clarification(self, request_id: str) -> ClarificationRequest:
        """Fetch one clarification request."""
        data = self.store.read()
        for row in data.get("clarifications", []):
            if row.get("request_id") == request_id:
                return ClarificationRequest(
                    work_item_id=int(row["work_item_id"]),
                    work_item_title=str(row["work_item_title"]),
                    questions=[str(item) for item in row.get("questions", [])],
                    status=str(row.get("status", "pending")),
                    answers={str(key): str(value) for key, value in row.get("answers", {}).items()},
                    requester=str(row.get("requester", "agent")),
                    request_id=str(row["request_id"]),
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                )
        raise KeyError(f"Clarification request not found: {request_id}")

    def _resolve_clarification_console(self, request_id: str) -> ClarificationRequest:
        clarification = self.get_clarification(request_id)
        answers: dict[str, str] = {}
        for question in clarification.questions:
            answer = input(f"\nClarification required: {question}\nAnswer: ").strip()
            answers[question] = answer
        self.submit_clarification_answers(
            request_id=request_id,
            responder="console-user",
            answers=answers,
        )
        return self.get_clarification(request_id)

    def _resolve_clarification_api_wait(self, request_id: str) -> ClarificationRequest:
        timeout = self.config.timeout_seconds
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            current = self.get_clarification(request_id)
            if current.status == "answered":
                return current
            time.sleep(5)

        self.update_clarification_status(
            request_id=request_id,
            status="timed_out",
            responder="system-timeout",
            answers={},
        )
        timed_out = self.get_clarification(request_id)
        self.logger.warning("clarification_timeout request_id=%s", request_id)
        return timed_out

    def submit_decision(self, request_id: str, approved: bool, approver: str, comment: str = "") -> bool:
        """Submit approval decision from chatbot/operator."""
        data = self.store.read()
        updated = False
        for row in data.get("requests", []):
            if row.get("request_id") == request_id:
                row["status"] = ApprovalStatus.APPROVED.value if approved else ApprovalStatus.REJECTED.value
                row["approver"] = approver
                row["comment"] = comment
                row["updated_at"] = datetime.now(UTC).isoformat()
                updated = True
                break
        if updated:
            self.store.write(data)
            self.logger.info("approval_decision_saved request_id=%s approved=%s", request_id, approved)
        return updated

    def update_approval_status(
        self,
        request_id: str,
        status: ApprovalStatus,
        approver: str,
        comment: str = "",
    ) -> bool:
        """Set approval request status directly."""
        data = self.store.read()
        updated = False
        for row in data.get("requests", []):
            if row.get("request_id") == request_id:
                row["status"] = status.value
                row["approver"] = approver
                row["comment"] = comment
                row["updated_at"] = datetime.now(UTC).isoformat()
                updated = True
                break
        if updated:
            self.store.write(data)
        return updated

    def request_approval(self, stage: str, summary: str) -> ApprovalRequest:
        """Create approval request and resolve according to configured mode."""
        request = ApprovalRequest(stage=stage, summary=summary)
        data = self.store.read()
        requests = data.setdefault("requests", [])
        requests.append(request.as_dict())
        self.store.write(data)
        self.logger.info("approval_requested stage=%s request_id=%s", stage, request.request_id)

        if stage in self.config.auto_approve_stages:
            self.submit_decision(
                request_id=request.request_id,
                approved=True,
                approver="auto-approver",
                comment="Auto-approved by config",
            )
            return self.get_request(request.request_id)

        mode = self.config.mode.lower().strip()
        if mode == "console":
            return self._resolve_console(request.request_id)
        if mode == "api":
            return self._resolve_api_wait(request.request_id)
        if mode == "auto":
            self.submit_decision(
                request_id=request.request_id,
                approved=True,
                approver="auto-mode",
                comment="Auto mode enabled",
            )
            return self.get_request(request.request_id)

        raise ValueError(f"Unsupported approval mode: {self.config.mode}")

    def get_request(self, request_id: str) -> ApprovalRequest:
        """Fetch one approval request and map to dataclass."""
        data = self.store.read()
        for row in data.get("requests", []):
            if row.get("request_id") == request_id:
                return ApprovalRequest(
                    stage=row["stage"],
                    summary=row["summary"],
                    status=ApprovalStatus(row["status"]),
                    approver=row.get("approver"),
                    comment=row.get("comment"),
                    request_id=row["request_id"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                )
        raise KeyError(f"Approval request not found: {request_id}")

    def get_request_row(self, request_id: str) -> dict:
        """Fetch raw request payload for API enrichment use-cases."""
        data = self.store.read()
        for row in data.get("requests", []):
            if row.get("request_id") == request_id:
                return row
        raise KeyError(f"Approval request not found: {request_id}")

    def _resolve_console(self, request_id: str) -> ApprovalRequest:
        prompt = (
            "\nApproval required. Type 'approve' to continue, 'reject' to stop: "
        )
        decision = input(prompt).strip().lower()
        approved = decision == "approve"
        self.submit_decision(
            request_id=request_id,
            approved=approved,
            approver="console-user",
            comment="Console decision",
        )
        return self.get_request(request_id)

    def _resolve_api_wait(self, request_id: str) -> ApprovalRequest:
        timeout = self.config.timeout_seconds
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            current = self.get_request(request_id)
            if current.status in {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED}:
                return current
            time.sleep(5)

        self.update_approval_status(
            request_id=request_id,
            status=ApprovalStatus.TIMED_OUT,
            approver="system-timeout",
            comment="Approval timed out",
        )
        timed_out = self.get_request(request_id)
        self.logger.warning("approval_timeout request_id=%s", request_id)
        return timed_out

    @staticmethod
    def _build_stage_guidance(stage: str) -> dict:
        """Build deterministic approval checklist by stage."""
        checklists = {
            "qe": [
                "Validate schema compatibility and data quality checks.",
                "Confirm unit and integration tests passed in pipeline artifacts.",
                "Review rollback plan and deployment notes.",
            ],
            "stg": [
                "Review performance and scalability metrics.",
                "Confirm RFC/CAB prerequisites are complete.",
                "Validate production-like data contract behavior.",
            ],
            "prod": [
                "Confirm final change window approval.",
                "Validate monitoring alerts and on-call readiness.",
                "Verify backup and rollback controls.",
            ],
        }
        stage_key = stage.lower().strip()
        guidance = checklists.get(stage_key, ["Review stage deployment evidence before approving."])
        priority = "high" if stage_key in {"prod"} else "medium"
        return {"recommended_action": "approve_if_all_checks_pass", "risk_level": priority, "checklist": guidance}
