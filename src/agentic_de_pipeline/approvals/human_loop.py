"""Human-in-the-loop approval workflow management."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from agentic_de_pipeline.config import ApprovalConfig
from agentic_de_pipeline.logging_utils import get_module_logger
from agentic_de_pipeline.models import ApprovalRequest, ApprovalStatus
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

        self.submit_decision(
            request_id=request_id,
            approved=False,
            approver="system-timeout",
            comment="Approval timed out",
        )
        timed_out = self.get_request(request_id)
        timed_out.status = ApprovalStatus.TIMED_OUT
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
