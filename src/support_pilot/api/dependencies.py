from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from support_pilot.auth.service import (
    authenticate_cookie_token,
    authenticate_token,
    record_auth_event,
)
from support_pilot.auth.sessions import verify_csrf
from support_pilot.config import get_settings
from support_pilot.domain.enums import UserStatus
from support_pilot.domain.errors import AuthenticationError, CsrfError
from support_pilot.infrastructure.database import get_db
from support_pilot.infrastructure.models import UserAccount
from support_pilot.infrastructure.repositories import SupportRepository

SessionDep = Annotated[Session, Depends(get_db)]
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
) -> UserAccount:
    """Resolve the caller from a bearer token, a browser session cookie, or the legacy header."""

    settings = get_settings()
    if credentials is not None:
        if credentials.scheme.casefold() != "bearer":
            record_auth_event(
                session,
                actor_id="anonymous",
                outcome="denied",
                reason_code="invalid_authorization_scheme",
            )
            raise AuthenticationError("Authorization scheme must be Bearer")
        try:
            return authenticate_token(session, credentials.credentials)
        except AuthenticationError:
            record_auth_event(
                session,
                actor_id="anonymous",
                outcome="denied",
                reason_code="invalid_bearer_token",
            )
            raise
    access_token = request.cookies.get(settings.auth_access_cookie)
    if access_token:
        return _authenticate_session_cookie(request, session, access_token=access_token)
    if not settings.allow_legacy_user_header:
        record_auth_event(
            session,
            actor_id="anonymous",
            outcome="denied",
            reason_code="bearer_token_missing",
        )
        raise AuthenticationError("Bearer token is required")
    if x_user_id is None:
        record_auth_event(
            session,
            actor_id="anonymous",
            outcome="denied",
            reason_code="authentication_missing",
        )
        raise AuthenticationError("Bearer token is required")
    try:
        user_id = UUID(x_user_id)
    except ValueError as error:
        raise AuthenticationError("X-User-Id must be a valid UUID") from error
    user = SupportRepository(session).get_user(user_id)
    if user is None or user.status != UserStatus.ACTIVE.value:
        raise AuthenticationError("active user not found")
    return user


def _authenticate_session_cookie(
    request: Request, session: Session, *, access_token: str
) -> UserAccount:
    settings = get_settings()
    try:
        user, auth_session = authenticate_cookie_token(session, access_token)
    except AuthenticationError:
        record_auth_event(
            session,
            actor_id="anonymous",
            outcome="denied",
            reason_code="invalid_session_cookie",
        )
        raise
    try:
        verify_csrf(
            auth_session,
            header_value=request.headers.get(settings.auth_csrf_header),
            cookie_value=request.cookies.get(settings.auth_csrf_cookie),
            method=request.method,
        )
    except CsrfError:
        record_auth_event(
            session,
            actor_id=str(user.id),
            outcome="denied",
            reason_code="csrf_token_invalid",
            tenant_id=user.tenant_id,
        )
        raise
    return user


CurrentUserDep = Annotated[UserAccount, Depends(get_current_user)]
