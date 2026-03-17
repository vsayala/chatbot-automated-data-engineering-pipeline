"""Chatbot-facing API for approvals and workflow control."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agentic_de_pipeline.config import load_config
from agentic_de_pipeline.workflow.bootstrap import build_orchestrator


class ApprovalDecisionPayload(BaseModel):
    """Payload for approval decision submissions."""

    approved: bool = Field(..., description="True to approve, False to reject")
    approver: str = Field(..., min_length=2, max_length=128)
    comment: str = Field(default="", max_length=500)


class ClarificationResponsePayload(BaseModel):
    """Payload for clarification responses from human approver."""

    responder: str = Field(..., min_length=2, max_length=128)
    answers: dict[str, str] = Field(default_factory=dict)


class ChatMessagePayload(BaseModel):
    """Payload for HIL chat messages to assistant."""

    message: str = Field(..., min_length=1, max_length=4000)
    context: dict[str, str] = Field(default_factory=dict)


def create_app(config_path: str) -> FastAPI:
    """Create and configure FastAPI app."""
    app = FastAPI(title="Agentic Data Engineering Chat API", version="0.1.0")
    config = load_config(config_path)
    orchestrator = build_orchestrator(config)
    frontend_dir = Path(__file__).resolve().parent / "frontend"

    @app.get("/ui")
    def ui_home() -> FileResponse:
        return FileResponse(frontend_dir / "index.html")

    @app.get("/ui/app.js")
    def ui_script() -> FileResponse:
        return FileResponse(frontend_dir / "app.js", media_type="application/javascript")

    @app.get("/ui/styles.css")
    def ui_styles() -> FileResponse:
        return FileResponse(frontend_dir / "styles.css", media_type="text/css")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/approvals/pending")
    def list_pending_approvals() -> dict[str, list[dict]]:
        pending = orchestrator.approval_service.list_pending()
        return {"pending": pending}

    @app.get("/clarifications/pending")
    def list_pending_clarifications() -> dict[str, list[dict]]:
        pending = orchestrator.approval_service.list_pending_clarifications()
        return {"pending": pending}

    @app.post("/clarifications/{request_id}/response")
    def submit_clarification_response(request_id: str, payload: ClarificationResponsePayload) -> dict[str, str]:
        updated = orchestrator.approval_service.submit_clarification_answers(
            request_id=request_id,
            responder=payload.responder,
            answers=payload.answers,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Clarification request not found")
        return {"status": "updated", "request_id": request_id}

    @app.get("/approvals/pending-with-suggestions")
    def list_pending_with_suggestions() -> dict[str, list[dict]]:
        pending = orchestrator.approval_service.list_pending_with_guidance()
        prompt_engine = orchestrator.requirement_agent.prompt_engine
        enriched: list[dict] = []
        for row in pending:
            guidance = row.get("guidance", {})
            suggestion_prompt = prompt_engine.render(
                "approval_suggestion",
                {
                    "stage": row.get("stage", ""),
                    "summary": row.get("summary", ""),
                    "checklist": guidance.get("checklist", []),
                    "risk_level": guidance.get("risk_level", "medium"),
                    "fallback": (
                        f"Stage {row.get('stage')} requires checklist validation before approval. "
                        "Approve only when all checks pass."
                    ),
                },
            )
            suggestion_text = prompt_engine.generate_text(suggestion_prompt)
            enriched.append({**row, "guidance": guidance, "suggestion_text": suggestion_text})
        return {"pending": enriched}

    @app.get("/approvals/{request_id}/suggestion")
    def get_approval_suggestion(request_id: str) -> dict:
        try:
            row = orchestrator.approval_service.get_request_row(request_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        guidance = orchestrator.approval_service.get_stage_guidance(str(row.get("stage", "")))
        prompt_engine = orchestrator.requirement_agent.prompt_engine
        suggestion_prompt = prompt_engine.render(
            "approval_suggestion",
            {
                "stage": row.get("stage", ""),
                "summary": row.get("summary", ""),
                "checklist": guidance.get("checklist", []),
                "risk_level": guidance.get("risk_level", "medium"),
                "fallback": f"Review checklist for stage {row.get('stage')}.",
            },
        )
        suggestion_text = prompt_engine.generate_text(suggestion_prompt)
        return {"request_id": request_id, "guidance": guidance, "suggestion_text": suggestion_text}

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
        if config.runtime.require_preflight_before_run:
            try:
                checks = orchestrator.preflight_validator.validate_or_raise()
            except Exception as exc:  # pylint: disable=broad-except
                raise HTTPException(status_code=503, detail=f"Preflight failed: {exc}") from exc
        else:
            checks = {"preflight": "skipped"}
        summary = orchestrator.run_once()
        if not summary:
            return {"status": "no_work_items", "preflight": checks}

        # Convert dataclass output for JSON response.
        response = asdict(summary)
        response["generated_at"] = summary.generated_at.isoformat()
        for stage in response["stage_results"]:
            stage["started_at"] = stage["started_at"].isoformat()
            stage["finished_at"] = stage["finished_at"].isoformat()
        response["preflight"] = checks
        return response

    @app.get("/preflight/run")
    def run_preflight() -> dict[str, dict[str, str]]:
        checks = orchestrator.preflight_validator.run_checks()
        return {"checks": checks}

    @app.get("/work-items/active")
    def list_active_work_items(limit: int = 50) -> dict[str, list[dict]]:
        items = orchestrator.list_active_work_items(limit=limit)
        return {"items": items}

    @app.post("/chat/message")
    def chat_message(payload: ChatMessagePayload) -> dict[str, str]:
        message = payload.message.strip()
        pending_approvals = len(orchestrator.approval_service.list_pending())
        pending_clarifications = len(orchestrator.approval_service.list_pending_clarifications())
        active_items = len(orchestrator.list_active_work_items(limit=100))
        prompt = orchestrator.requirement_agent.prompt_engine.render(
            "hil_chat_response",
            {
                "message": message,
                "context": payload.context,
                "pending_approvals": pending_approvals,
                "pending_clarifications": pending_clarifications,
                "active_items": active_items,
                "fallback": (
                    "I can help with workflow control. "
                    f"Pending approvals={pending_approvals}, pending clarifications={pending_clarifications}, "
                    f"active items={active_items}. Request received: {message}"
                ),
            },
        )
        response = orchestrator.requirement_agent.prompt_engine.generate_text(prompt)
        return {"response": response}

    return app
