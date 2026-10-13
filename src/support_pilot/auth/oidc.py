from base64 import urlsafe_b64encode
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from typing import Any

import httpx
import jwt
from jwt.exceptions import InvalidTokenError, PyJWKError
from sqlalchemy import select
from sqlalchemy.orm import Session

from support_pilot.config import Settings, get_settings
from support_pilot.domain.enums import UserStatus
from support_pilot.domain.errors import AuthenticationError, DomainError
from support_pilot.infrastructure.models import OidcLoginRequest, UserAccount, UserIdentity

CODE_CHALLENGE_METHOD = "S256"
ALLOWED_SIGNING_ALGORITHMS = frozenset({"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"})


class OidcNotConfiguredError(DomainError):
    status_code = 503
    code = "oidc_not_configured"


class OidcFlowError(DomainError):
    """The authorization code flow failed verification at some step."""

    status_code = 400
    code = "oidc_flow_failed"


class OidcAccountNotLinkedError(DomainError):
    status_code = 403
    code = "oidc_account_not_linked"


@dataclass(frozen=True)
class OidcMetadata:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str


@dataclass(frozen=True)
class OidcIdentity:
    issuer: str
    subject: str
    email: str
    display_name: str | None


@dataclass(frozen=True)
class OidcLoginStart:
    state: str
    nonce: str
    code_verifier: str
    authorization_url: str


def hash_state(state: str) -> str:
    return sha256(state.encode("utf-8")).hexdigest()


def generate_pkce_pair() -> tuple[str, str]:
    """Return ``(verifier, challenge)`` for the S256 PKCE method."""

    verifier = token_urlsafe(64)[:96]
    digest = sha256(verifier.encode("ascii")).digest()
    challenge = urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def ensure_configured(settings: Settings | None = None) -> Settings:
    resolved = settings or get_settings()
    if not resolved.oidc_enabled:
        raise OidcNotConfiguredError("OIDC login is not enabled on this deployment")
    if not resolved.oidc_issuer or not resolved.oidc_client_id or not resolved.oidc_redirect_uri:
        raise OidcNotConfiguredError("OIDC issuer, client id and redirect uri are required")
    return resolved


def fetch_metadata(settings: Settings, *, client: httpx.Client) -> OidcMetadata:
    url = f"{settings.oidc_issuer}/.well-known/openid-configuration"
    document = _get_json(client, url, settings=settings)
    issuer = str(document.get("issuer", ""))
    if issuer.rstrip("/") != settings.oidc_issuer.rstrip("/"):
        raise OidcFlowError("discovery document issuer does not match the configured issuer")
    try:
        return OidcMetadata(
            issuer=issuer,
            authorization_endpoint=str(document["authorization_endpoint"]),
            token_endpoint=str(document["token_endpoint"]),
            jwks_uri=str(document["jwks_uri"]),
        )
    except KeyError as error:
        raise OidcFlowError(f"discovery document is missing {error}") from error


def build_authorization_url(
    metadata: OidcMetadata,
    settings: Settings,
    *,
    state: str,
    nonce: str,
    code_challenge: str,
) -> str:
    params = {
        "response_type": "code",
        "client_id": settings.oidc_client_id,
        "redirect_uri": settings.oidc_redirect_uri,
        "scope": settings.oidc_scopes,
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": CODE_CHALLENGE_METHOD,
    }
    return str(httpx.URL(metadata.authorization_endpoint, params=params))


def exchange_authorization_code(
    settings: Settings,
    metadata: OidcMetadata,
    *,
    code: str,
    code_verifier: str,
    client: httpx.Client,
) -> str:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.oidc_redirect_uri,
        "client_id": settings.oidc_client_id,
        "code_verifier": code_verifier,
    }
    secret = settings.oidc_client_secret.get_secret_value()
    if secret:
        data["client_secret"] = secret
    try:
        response = client.post(
            metadata.token_endpoint, data=data, timeout=settings.oidc_timeout_seconds
        )
    except httpx.HTTPError as error:
        raise OidcFlowError(f"token endpoint is unreachable: {error}") from error
    if response.status_code >= 400:
        raise OidcFlowError("token endpoint rejected the authorization code")
    try:
        payload = response.json()
    except ValueError as error:
        raise OidcFlowError("token endpoint did not return JSON") from error
    id_token = payload.get("id_token") if isinstance(payload, dict) else None
    if not isinstance(id_token, str) or not id_token:
        raise OidcFlowError("token response did not contain an id_token")
    return id_token


def verify_id_token(
    settings: Settings,
    metadata: OidcMetadata,
    id_token: str,
    *,
    nonce: str,
    client: httpx.Client,
) -> OidcIdentity:
    header = _unverified_header(id_token)
    algorithm = str(header.get("alg", ""))
    if algorithm not in ALLOWED_SIGNING_ALGORITHMS:
        raise OidcFlowError(f"id_token signing algorithm {algorithm!r} is not accepted")
    signing_key = _select_signing_key(
        settings, metadata, client=client, key_id=header.get("kid")
    )
    try:
        claims = jwt.decode(
            id_token,
            signing_key,
            algorithms=[algorithm],
            audience=settings.oidc_client_id,
            issuer=metadata.issuer,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except InvalidTokenError as error:
        raise OidcFlowError(f"id_token verification failed: {error}") from error
    if claims.get("nonce") != nonce:
        raise OidcFlowError("id_token nonce does not match the login request")
    email = claims.get("email")
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise OidcFlowError("id_token is missing the subject claim")
    if not isinstance(email, str) or not email:
        raise OidcFlowError("id_token is missing the email claim")
    if claims.get("email_verified") is not True:
        raise OidcFlowError("id_token email is not verified by the identity provider")
    display_name = claims.get("name")
    return OidcIdentity(
        issuer=metadata.issuer,
        subject=subject,
        email=email.casefold(),
        display_name=display_name if isinstance(display_name, str) else None,
    )


def start_login(
    session: Session,
    *,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> OidcLoginStart:
    resolved = ensure_configured(settings)
    with use_client(client, resolved) as http:
        metadata = fetch_metadata(resolved, client=http)
        state = token_urlsafe(32)
        nonce = token_urlsafe(32)
        verifier, challenge = generate_pkce_pair()
        authorization_url = build_authorization_url(
            metadata, resolved, state=state, nonce=nonce, code_challenge=challenge
        )
    session.add(
        OidcLoginRequest(
            state_hash=hash_state(state),
            nonce=nonce,
            code_verifier=verifier,
            redirect_uri=resolved.oidc_redirect_uri,
            expires_at=datetime.now(UTC) + timedelta(seconds=resolved.oidc_request_ttl_seconds),
        )
    )
    session.commit()
    return OidcLoginStart(
        state=state, nonce=nonce, code_verifier=verifier, authorization_url=authorization_url
    )


def consume_login_request(session: Session, *, state: str) -> OidcLoginRequest:
    """Look up and burn the pending login request for ``state``."""

    if not state:
        raise OidcFlowError("state parameter is missing")
    row = session.scalar(
        select(OidcLoginRequest).where(OidcLoginRequest.state_hash == hash_state(state))
    )
    now = datetime.now(UTC)
    expires_at = row.expires_at if row is not None else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if row is None or row.consumed_at is not None or expires_at is None or expires_at <= now:
        raise OidcFlowError("login request is unknown, already used or expired")
    row.consumed_at = now
    session.commit()
    return row


def complete_login(
    session: Session,
    *,
    state: str,
    code: str,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> UserAccount:
    resolved = ensure_configured(settings)
    request_row = consume_login_request(session, state=state)
    with use_client(client, resolved) as http:
        metadata = fetch_metadata(resolved, client=http)
        id_token = exchange_authorization_code(
            resolved,
            metadata,
            code=code,
            code_verifier=request_row.code_verifier,
            client=http,
        )
        identity = verify_id_token(
            resolved, metadata, id_token, nonce=request_row.nonce, client=http
        )
    return resolve_user(session, identity)


def resolve_user(session: Session, identity: OidcIdentity) -> UserAccount:
    """Link by verified email; never create accounts implicitly."""

    binding = session.scalar(
        select(UserIdentity).where(
            UserIdentity.issuer == identity.issuer,
            UserIdentity.subject == identity.subject,
        )
    )
    if binding is not None:
        user = session.get(UserAccount, binding.user_id)
        if user is None or user.status != UserStatus.ACTIVE.value:
            raise AuthenticationError("linked account is no longer active")
        return user
    user = session.scalar(select(UserAccount).where(UserAccount.email == identity.email))
    if user is None or user.status != UserStatus.ACTIVE.value:
        raise OidcAccountNotLinkedError(
            "no active SupportPilot account matches this verified email address"
        )
    session.add(
        UserIdentity(
            user_id=user.id,
            issuer=identity.issuer,
            subject=identity.subject,
            email=identity.email,
        )
    )
    session.commit()
    return user


@contextmanager
def use_client(
    client: httpx.Client | None, settings: Settings
) -> Iterator[httpx.Client]:
    """Reuse an injected client without closing it, otherwise open a short-lived one."""

    if client is not None:
        yield client
        return
    with httpx.Client(timeout=settings.oidc_timeout_seconds) as created:
        yield created


def _unverified_header(id_token: str) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(id_token)
    except InvalidTokenError as error:
        raise OidcFlowError(f"id_token is not a JWT: {error}") from error
    if not isinstance(header, dict):
        raise OidcFlowError("id_token header is malformed")
    return header


def _select_signing_key(
    settings: Settings,
    metadata: OidcMetadata,
    *,
    client: httpx.Client,
    key_id: object,
) -> Any:
    document = _get_json(client, metadata.jwks_uri, settings=settings)
    keys = document.get("keys")
    if not isinstance(keys, list) or not keys:
        raise OidcFlowError("JWKS document does not contain any keys")
    try:
        key_set = jwt.PyJWKSet.from_dict(document)
    except (PyJWKError, InvalidTokenError, ValueError) as error:
        raise OidcFlowError(f"JWKS document could not be parsed: {error}") from error
    for key in key_set.keys:
        matches_id = key_id is None or key.key_id == key_id
        if matches_id and getattr(key, "algorithm_name", None) in ALLOWED_SIGNING_ALGORITHMS:
            return key
    raise OidcFlowError("no usable signing key matches the id_token")


def _get_json(client: httpx.Client, url: str, *, settings: Settings) -> dict[str, Any]:
    try:
        response = client.get(url, timeout=settings.oidc_timeout_seconds)
    except httpx.HTTPError as error:
        raise OidcFlowError(f"{url} is unreachable: {error}") from error
    if response.status_code >= 400:
        raise OidcFlowError(f"{url} returned HTTP {response.status_code}")
    try:
        document = response.json()
    except ValueError as error:
        raise OidcFlowError(f"{url} did not return JSON") from error
    if not isinstance(document, dict):
        raise OidcFlowError(f"{url} did not return a JSON object")
    return document
