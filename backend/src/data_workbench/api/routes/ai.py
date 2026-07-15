from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from data_workbench.ai.gateway import AiGateway
from data_workbench.storage.session_repository import SessionRepository

router = APIRouter()


class AiPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_samples: dict[str, list[str]] = Field(default_factory=dict)


class AiApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preview_id: str


def _profile_or_error(request: Request, session_id: str) -> dict[str, Any]:
    repo: SessionRepository = request.app.state.session_repository
    if repo.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    saved = repo.load_profile(session_id)
    if saved is None:
        raise HTTPException(
            status_code=409, detail="AI suggestions require a profiled session"
        )
    profile: dict[str, Any] = saved["profile"]  # type: ignore[assignment]
    return profile


def get_gateway(request: Request) -> AiGateway:
    gateway: AiGateway = request.app.state.ai_gateway
    return gateway


@router.post("/api/sessions/{session_id}/ai/dictionary/preview")
def preview_ai_dictionary(
    request: Request,
    session_id: str,
    payload: AiPreviewRequest,
    gateway: AiGateway = Depends(get_gateway),
) -> dict[str, object]:
    profile = _profile_or_error(request, session_id)
    preview = gateway.preview_dictionary_request(profile, payload.selected_samples)
    return preview.model_dump(mode="json")


@router.post("/api/sessions/{session_id}/ai/dictionary/approve")
def approve_ai_dictionary(
    request: Request,
    session_id: str,
    payload: AiApproveRequest,
    gateway: AiGateway = Depends(get_gateway),
) -> dict[str, object]:
    profile = _profile_or_error(request, session_id)
    attempt = gateway.approve_or_fallback(payload.preview_id, profile)
    return attempt.model_dump(mode="json")
