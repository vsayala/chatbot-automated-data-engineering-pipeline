"""Chatbot-facing API for approvals and workflow control."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agentic_de_pipeline.config import load_config
from agentic_de_pipeline.workflow.bootstrap import build_orchestrator


class ApprovalDecisionPayload(BaseModel):
    """Payload for approval decision submissions."""

    approved: bool = Field(..., description="True to approve, False to reject")
    approver: str = Field(..., min_length=2, max_length=128)
    comment: str = Field(default="", max_length=500)


def create_app(config_path: str) -> FastAPI:
    """Create and configure FastAPI app."""
    app = FastAPI(title="Agentic Data Engineering Chat API", version="0.1.0")
    config = load_config(config_path)
    orchestrator = build_orchestrator(config)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/approvals/pending")
    def list_pending_approvals() -> dict[str, list[dict]]:
        pending = orchestrator.approval_service.list_pending()
        return {"pending": pending}

    @app.post("/approvals/{request_id}/decision")
    def submit_approval_decision(request_id: str, payload: ApprovalDecisionPayload) -> dict[str, str]:
        updated = orchestrator.approval_service.submit_decision(
            request_id=request_id,
            approved=payload.approved,
            approver=payload.approver,
            comment=payload.comment,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Approval request not found")
        return {"status": "updated", "request_id": request_id}

    @app.post("/workflow/process-next")
    def process_next_work_item() -> dict:
        summary = orchestrator.run_once()
        if not summary:
            return {"status": "no_work_items"}

        # Convert dataclass output for JSON response.
        response = asdict(summary)
        response["generated_at"] = summary.generated_at.isoformat()
        for stage in response["stage_results"]:
            stage["started_at"] = stage["started_at"].isoformat()
            stage["finished_at"] = stage["finished_at"].isoformat()
        return response

    return app
