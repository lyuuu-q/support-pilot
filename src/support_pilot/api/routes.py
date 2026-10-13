import json
from collections.abc import Iterator
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from support_pilot.agent.contracts import (
    AgentRequest,
    AgentResponse,
    RunEventListResponse,
    RunEventResponse,
)
from support_pilot.agent.providers import get_decision_provider
from support_pilot.agent.service import AgentService
from support_pilot.api.dependencies import CurrentUserDep, SessionDep
from support_pilot.api.schemas import ErrorResponse
from support_pilot.application.contracts import SupportInput, SupportResponse
from support_pilot.application.services import SupportService
from support_pilot.auth.contracts import (
    AuthSessionListResponse,
    AuthSessionResponse,
    CurrentUserResponse,
    LoginRequest,
    LoginResponse,
    TokenResponse,
)
from support_pilot.auth.service import authenticate_user, issue_access_token, record_auth_event
from support_pilot.auth.sessions import (
    IssuedSession,
    find_active_session,
    list_active_sessions,
    lookup_session,
    revoke_all_user_sessions,
    revoke_session,
    revoke_user_session,
    rotate_session,
    session_id_from_access_token,
    start_session,
    verify_csrf,
)
from support_pilot.channels.factory import get_outbound_channel
from support_pilot.config import get_settings
from support_pilot.domain.enums import TicketStatus
from support_pilot.domain.errors import (
    AuthenticationError,
    DomainError,
    ResourceNotFoundError,
)
from support_pilot.infrastructure.models import UserAccount
from support_pilot.infrastructure.repositories import SupportRepository
from support_pilot.rag.contracts import KnowledgeSearchInput, KnowledgeSearchResponse
from support_pilot.rag.providers.factory import get_provider_bundle
from support_pilot.rag.retrieval import HybridRetrievalService
from support_pilot.telemetry import record_session_revoked, record_session_started
from support_pilot.tickets.contracts import (
    ClaimTicketRequest,
    HumanFeedbackRequest,
    HumanFeedbackResponse,
    TicketListResponse,
    TicketResponse,
    TransitionTicketRequest,
)
from support_pilot.tickets.service import TicketWorkflowService

router = APIRouter(prefix="/api/v1")


def _sse_event(event: str, payload: Any, *, event_id: str | None = None) -> str:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    id_line = f"id: {event_id}\n" if event_id is not None else ""
    return f"{id_line}event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"


def _current_user_response(user: UserAccount) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
    )


def _set_session_cookies(
    response: Response,
    *,
    access_token: str,
    material: IssuedSession,
) -> None:
    settings = get_settings()
    refresh_max_age = settings.auth_refresh_token_days * 86_400
    response.set_cookie(
        settings.auth_access_cookie,
        access_token,
        max_age=settings.jwt_access_token_minutes * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=COOKIE_SAMESITE,
        path="/",
    )
    response.set_cookie(
        settings.auth_refresh_cookie,
        material.refresh_token,
        max_age=refresh_max_age,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=COOKIE_SAMESITE,
        path=settings.auth_refresh_cookie_path,
    )
    response.set_cookie(
        settings.auth_csrf_cookie,
        material.csrf_token,
        max_age=refresh_max_age,
        httponly=False,
        secure=settings.auth_cookie_secure,
        samesite=COOKIE_SAMESITE,
        path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        settings.auth_access_cookie,
        path="/",
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=COOKIE_SAMESITE,
    )
    response.delete_cookie(
        settings.auth_refresh_cookie,
        path=settings.auth_refresh_cookie_path,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=COOKIE_SAMESITE,
    )
    response.delete_cookie(
        settings.auth_csrf_cookie,
        path="/",
        httponly=False,
        secure=settings.auth_cookie_secure,
        samesite=COOKIE_SAMESITE,
    )


@router.post(
    "/auth/login",
    response_model=TokenResponse | LoginResponse,
    responses={401: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    tags=["auth"],
)
def login(
    request: LoginRequest, response: Response, session: SessionDep
) -> TokenResponse | LoginResponse:
    """Authenticate, then either start a cookie session or mint a bearer token."""

    settings = get_settings()
    user = authenticate_user(session, email=request.email, password=request.password)
    if request.session_mode == "token":
        return issue_access_token(user, settings=settings)
    row, material = start_session(session, user, settings=settings)
    token = issue_access_token(user, settings=settings, session_id=row.id)
    session.commit()
    record_session_started()
    _set_session_cookies(response, access_token=token.access_token, material=material)
    return LoginResponse(
        user=_current_user_response(user),
        csrf_token=material.csrf_token,
        expires_in=token.expires_in,
    )


@router.post(
    "/auth/refresh",
    response_model=LoginResponse,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
    tags=["auth"],
)
def refresh_session(request: Request, response: Response, session: SessionDep) -> LoginResponse:
    """Rotate the refresh token and hand the browser a fresh cookie pair."""

    settings = get_settings()
    refresh_token = request.cookies.get(settings.auth_refresh_cookie)
    previous = find_active_session(session, refresh_token)
    verify_csrf(
        previous,
        header_value=request.headers.get(settings.auth_csrf_header),
        cookie_value=request.cookies.get(settings.auth_csrf_cookie),
        method=request.method,
    )
    user = SupportRepository(session).get_user(previous.user_id)
    if user is None:
        raise AuthenticationError("refresh session user no longer exists")
    row, material = rotate_session(session, refresh_token, settings=settings)
    token = issue_access_token(user, settings=settings, session_id=row.id)
    session.commit()
    _set_session_cookies(response, access_token=token.access_token, material=material)
    return LoginResponse(
        user=_current_user_response(user),
        csrf_token=material.csrf_token,
        expires_in=token.expires_in,
    )


@router.post(
    "/auth/logout",
    status_code=204,
    responses={403: {"model": ErrorResponse}},
    tags=["auth"],
)
def logout(request: Request, session: SessionDep) -> Response:
    """Revoke the presented session and clear every session cookie."""

    settings = get_settings()
    row = lookup_session(session, request.cookies.get(settings.auth_refresh_cookie))
    if row is not None:
        verify_csrf(
            row,
            header_value=request.headers.get(settings.auth_csrf_header),
            cookie_value=request.cookies.get(settings.auth_csrf_cookie),
            method=request.method,
        )
        if revoke_session(session, session_id=row.id) is not None:
            session.commit()
            record_session_revoked(reason="logout")
            record_auth_event(
                session,
                actor_id=str(row.user_id),
                outcome="success",
                reason_code="session_revoked",
                action="auth.session.revoke",
                resource_id=str(row.id),
            )
    response = Response(status_code=204)
    _clear_session_cookies(response)
    return response


@router.get(
    "/auth/sessions",
    response_model=AuthSessionListResponse,
    responses={401: {"model": ErrorResponse}},
    tags=["auth"],
)
def list_sessions(
    request: Request,
    session: SessionDep,
    actor: CurrentUserDep,
) -> AuthSessionListResponse:
    """List the caller's active browser sessions."""

    settings = get_settings()
    current_id = session_id_from_access_token(
        request.cookies.get(settings.auth_access_cookie), settings=settings
    )
    rows = list_active_sessions(session, user_id=actor.id)
    return AuthSessionListResponse(
        items=[
            AuthSessionResponse(
                id=row.id,
                user_agent=row.user_agent,
                issued_at=row.issued_at,
                expires_at=row.expires_at,
                current=row.id == current_id,
            )
            for row in rows
        ]
    )


@router.post(
    "/auth/sessions/{session_id}/revoke",
    status_code=204,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    tags=["auth"],
)
def revoke_own_session(
    session_id: UUID,
    request: Request,
    session: SessionDep,
    actor: CurrentUserDep,
) -> Response:
    """Revoke one of the caller's sessions, clearing cookies when it is the current one."""

    settings = get_settings()
    row = revoke_user_session(session, session_id=session_id, user_id=actor.id)
    if row is None:
        raise ResourceNotFoundError("active session not found for this account")
    session.commit()
    record_session_revoked(reason="owner")
    record_auth_event(
        session,
        actor_id=str(actor.id),
        outcome="success",
        reason_code="session_revoked_by_owner",
        tenant_id=actor.tenant_id,
        action="auth.session.revoke",
        resource_id=str(row.id),
    )
    response = Response(status_code=204)
    current_id = session_id_from_access_token(
        request.cookies.get(settings.auth_access_cookie), settings=settings
    )
    if current_id == row.id:
        _clear_session_cookies(response)
    return response


@router.post(
    "/auth/logout-all",
    status_code=204,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
    tags=["auth"],
)
def logout_all_sessions(
    session: SessionDep,
    actor: CurrentUserDep,
) -> Response:
    """Revoke every active session of the caller, not only the current one."""

    revoked = revoke_all_user_sessions(session, user_id=actor.id)
    session.commit()
    if revoked:
        record_session_revoked(reason="logout_all")
        record_auth_event(
            session,
            actor_id=str(actor.id),
            outcome="success",
            reason_code="all_sessions_revoked",
            tenant_id=actor.tenant_id,
            action="auth.session.revoke_all",
            resource_id=str(actor.id),
        )
    response = Response(status_code=204)
    _clear_session_cookies(response)
    return response


@router.get("/auth/me", response_model=CurrentUserResponse, tags=["auth"])
def current_user(actor: CurrentUserDep) -> CurrentUserResponse:
    return _current_user_response(actor)


@router.get("/tickets", response_model=TicketListResponse, tags=["tickets"])
def list_tickets(
    actor: CurrentUserDep,
    session: SessionDep,
    tenant_id: UUID | None = None,
    status: TicketStatus | None = None,
    q: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    cursor: Annotated[str | None, Query(min_length=1, max_length=500)] = None,
) -> TicketListResponse:
    return TicketWorkflowService(session).list_tickets(
        actor=actor,
        tenant_id=tenant_id,
        status=status,
        q=q,
        limit=limit,
        offset=offset,
        cursor=cursor,
    )


@router.get(
    "/tickets/{ticket_id}",
    response_model=TicketResponse,
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    tags=["tickets"],
)
def get_ticket(ticket_id: UUID, actor: CurrentUserDep, session: SessionDep) -> TicketResponse:
    return TicketWorkflowService(session).get_ticket(ticket_id, actor=actor)


@router.post(
    "/tickets/{ticket_id}/claim",
    response_model=TicketResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
    tags=["tickets"],
)
def claim_ticket(
    ticket_id: UUID,
    request: ClaimTicketRequest,
    actor: CurrentUserDep,
    session: SessionDep,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=100)
    ] = None,
) -> TicketResponse:
    return TicketWorkflowService(session).claim_ticket(
        ticket_id,
        request,
        actor=actor,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/tickets/{ticket_id}/transitions",
    response_model=TicketResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
    tags=["tickets"],
)
def transition_ticket(
    ticket_id: UUID,
    request: TransitionTicketRequest,
    actor: CurrentUserDep,
    session: SessionDep,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=100)
    ] = None,
) -> TicketResponse:
    return TicketWorkflowService(session).transition_ticket(
        ticket_id,
        request,
        actor=actor,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/tickets/{ticket_id}/feedback",
    response_model=HumanFeedbackResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
    tags=["tickets"],
)
def submit_feedback(
    ticket_id: UUID,
    request: HumanFeedbackRequest,
    actor: CurrentUserDep,
    session: SessionDep,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=100)
    ] = None,
) -> HumanFeedbackResponse:
    return TicketWorkflowService(session).submit_feedback(
        ticket_id,
        request,
        actor=actor,
        idempotency_key=idempotency_key,
    )


@router.get("/health/live", tags=["health"])
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", tags=["health"])
def readiness(session: SessionDep) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    return {"status": "ready"}


@router.post(
    "/support/resolve",
    response_model=SupportResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
    tags=["support"],
)
def resolve_support_request(
    request: SupportInput,
    actor: CurrentUserDep,
    session: SessionDep,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=100)
    ] = None,
) -> SupportResponse:
    return SupportService(session, channel=get_outbound_channel()).process(
        request,
        actor=actor,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/knowledge/search",
    response_model=KnowledgeSearchResponse,
    tags=["knowledge"],
)
def search_knowledge(
    request: KnowledgeSearchInput,
    session: SessionDep,
) -> KnowledgeSearchResponse:
    embedding_provider, reranker_provider = get_provider_bundle()
    return HybridRetrievalService(
        session,
        embedding_provider=embedding_provider,
        reranker_provider=reranker_provider,
    ).search(request)


@router.post(
    "/agent/resolve",
    response_model=AgentResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
    tags=["agent"],
)
def resolve_agent_request(
    request: AgentRequest,
    actor: CurrentUserDep,
    session: SessionDep,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=100)
    ] = None,
) -> AgentResponse:
    embedding_provider, reranker_provider = get_provider_bundle()
    return AgentService(
        session,
        decision_provider=get_decision_provider(),
        embedding_provider=embedding_provider,
        reranker_provider=reranker_provider,
    ).resolve(request, actor=actor, idempotency_key=idempotency_key)


@router.post(
    "/agent/runs/{run_id}/resume",
    response_model=AgentResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
    tags=["agent"],
)
def resume_agent_run(
    run_id: UUID,
    actor: CurrentUserDep,
    session: SessionDep,
) -> AgentResponse:
    embedding_provider, reranker_provider = get_provider_bundle()
    return AgentService(
        session,
        decision_provider=get_decision_provider(),
        embedding_provider=embedding_provider,
        reranker_provider=reranker_provider,
    ).resume_run(run_id, actor=actor)


@router.get(
    "/agent/runs/{run_id}/events",
    response_model=RunEventListResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
    tags=["agent"],
)
def list_agent_run_events(
    run_id: UUID,
    actor: CurrentUserDep,
    session: SessionDep,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> RunEventListResponse:
    embedding_provider, reranker_provider = get_provider_bundle()
    events = AgentService(
        session,
        decision_provider=get_decision_provider(),
        embedding_provider=embedding_provider,
        reranker_provider=reranker_provider,
    ).list_run_events(run_id, actor=actor, after=after, limit=limit)
    return RunEventListResponse(
        items=[
            RunEventResponse(
                sequence=event.sequence,
                event=event.event_name,
                payload=event.payload,
                event_id=event.event_id,
            )
            for event in events
        ]
    )


@router.post(
    "/agent/resolve/stream",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/event-stream": {}},
            "description": "LangGraph node progress followed by one result event",
        },
        401: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
    tags=["agent"],
)
def stream_agent_request(
    request: AgentRequest,
    actor: CurrentUserDep,
    session: SessionDep,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=100)
    ] = None,
) -> StreamingResponse:
    embedding_provider, reranker_provider = get_provider_bundle()
    service = AgentService(
        session,
        decision_provider=get_decision_provider(),
        embedding_provider=embedding_provider,
        reranker_provider=reranker_provider,
    )

    def event_stream() -> Iterator[str]:
        try:
            for event in service.resolve_events(
                request,
                actor=actor,
                idempotency_key=idempotency_key,
            ):
                yield _sse_event(event.name, event.payload, event_id=event.event_id)
        except DomainError as error:
            yield _sse_event(
                "error",
                {"error": {"code": error.code, "message": str(error)}},
                event_id=f"{request.session_id}:error",
            )
        except Exception:
            yield _sse_event(
                "error",
                {
                    "error": {
                        "code": "unexpected_agent_failure",
                        "message": "Agent execution failed; retry or request human support.",
                    }
                },
                event_id=f"{request.session_id}:error",
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
