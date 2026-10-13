from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient
from pydantic import SecretStr
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.orm import Session

from support_pilot.api.dependencies import get_oidc_client
from support_pilot.auth import oidc
from support_pilot.config import Settings
from support_pilot.infrastructure.models import AuditEvent, OidcLoginRequest, UserIdentity
from support_pilot.main import app

ISSUER = "https://idp.test"
CLIENT_ID = "support-pilot-console"
REDIRECT_URI = "http://testserver/api/v1/auth/oidc/callback"
JWT_SECRET = "unit-test-jwt-secret-with-at-least-32-characters"
CUSTOMER_EMAIL = "beta.developer@example.com"
SUBJECT = "idp-subject-1"


def _b64(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _challenge_for(verifier: str) -> str:
    digest = sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class FakeIdentityProvider:
    """Minimal OIDC provider: discovery, JWKS, authorization code + PKCE token endpoint."""

    def __init__(self) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = "test-key-1"
        self.challenge: str | None = None
        self.nonce: str | None = None
        self.verifiers_seen: dict[str, str] = {}

    # --- token minting -------------------------------------------------
    def public_secret_lookalike(self) -> str:
        """Public key material as text, i.e. exactly what an HS256 confusion attack needs."""

        der = self.key.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
        return base64.urlsafe_b64encode(der).decode("ascii")

    def public_jwk(self) -> dict[str, str]:
        numbers = self.key.public_key().public_numbers()
        return {
            "kty": "RSA",
            "kid": self.kid,
            "use": "sig",
            "alg": "RS256",
            "n": _b64(numbers.n),
            "e": _b64(numbers.e),
        }

    def id_token(
        self,
        *,
        nonce: str | None = None,
        audience: str = CLIENT_ID,
        email: str = CUSTOMER_EMAIL,
        email_verified: bool = True,
        subject: str = SUBJECT,
        expires_in: int = 300,
        algorithm: str = "RS256",
        kid: str | None = None,
        signing_key: object | None = None,
    ) -> str:
        now = datetime.now(UTC)
        payload = {
            "iss": ISSUER,
            "aud": audience,
            "sub": subject,
            "email": email,
            "email_verified": email_verified,
            "name": "Beta Developer",
            "iat": now,
            "exp": now + timedelta(seconds=expires_in),
            "nonce": nonce if nonce is not None else (self.nonce or ""),
        }
        key = signing_key if signing_key is not None else self.key
        return jwt.encode(payload, key, algorithm=algorithm, headers={"kid": kid or self.kid})

    # --- HTTP surface --------------------------------------------------
    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path == "/.well-known/openid-configuration":
                return httpx.Response(
                    200,
                    json={
                        "issuer": ISSUER,
                        "authorization_endpoint": f"{ISSUER}/authorize",
                        "token_endpoint": f"{ISSUER}/token",
                        "jwks_uri": f"{ISSUER}/jwks.json",
                    },
                )
            if path == "/jwks.json":
                return httpx.Response(200, json={"keys": [self.public_jwk()]})
            if path == "/token":
                form = parse_qs(request.content.decode())
                code = form.get("code", [""])[0]
                verifier = form.get("code_verifier", [""])[0]
                if self.challenge is None or _challenge_for(verifier) != self.challenge:
                    return httpx.Response(400, json={"error": "invalid_grant"})
                if form.get("client_id", [""])[0] != CLIENT_ID:
                    return httpx.Response(400, json={"error": "invalid_client"})
                self.verifiers_seen[code] = verifier
                return httpx.Response(
                    200,
                    json={
                        "access_token": "idp-access-token",
                        "token_type": "Bearer",
                        "id_token": self.id_token(),
                    },
                )
            return httpx.Response(404, json={"error": "not_found"})

        return httpx.MockTransport(handler)


@pytest.fixture()
def idp() -> FakeIdentityProvider:
    return FakeIdentityProvider()


@pytest.fixture()
def idp_http(idp: FakeIdentityProvider) -> httpx.Client:
    return httpx.Client(transport=idp.transport(), base_url=ISSUER)


@pytest.fixture()
def oidc_settings(monkeypatch: MonkeyPatch) -> Settings:
    settings = Settings(
        _env_file=None,
        oidc_enabled=True,
        oidc_issuer=ISSUER,
        oidc_client_id=CLIENT_ID,
        oidc_redirect_uri=REDIRECT_URI,
        jwt_secret=SecretStr(JWT_SECRET),
    )
    monkeypatch.setattr("support_pilot.auth.oidc.get_settings", lambda: settings)
    monkeypatch.setattr("support_pilot.api.routes.get_settings", lambda: settings)
    return settings


def _wire(client: TestClient, http: httpx.Client) -> None:
    app.dependency_overrides[get_oidc_client] = lambda: http


def _start(client: TestClient, idp: FakeIdentityProvider) -> tuple[str, dict[str, list[str]]]:
    response = client.get("/api/v1/auth/oidc/start", follow_redirects=False)
    assert response.status_code == 302
    parsed = urlparse(response.headers["location"])
    params = parse_qs(parsed.query)
    idp.challenge = params["code_challenge"][0]
    idp.nonce = params["nonce"][0]
    return response.headers["location"], params


def test_authorization_code_flow_links_identity_and_issues_cookie_session(
    client: TestClient,
    db_session: Session,
    idp: FakeIdentityProvider,
    idp_http: httpx.Client,
    oidc_settings: Settings,
) -> None:
    _wire(client, idp_http)

    location, params = _start(client, idp)

    parsed = urlparse(location)
    assert parsed.netloc == "idp.test"
    assert parsed.path == "/authorize"
    assert params["client_id"] == [CLIENT_ID]
    assert params["redirect_uri"] == [REDIRECT_URI]
    assert params["response_type"] == ["code"]
    assert params["scope"] == ["openid profile email"]
    assert params["code_challenge_method"] == ["S256"]
    assert len(params["code_challenge"][0]) == 43
    state = params["state"][0]
    assert oidc.hash_state(state) != state

    pending = db_session.scalar(select(OidcLoginRequest))
    assert pending is not None
    assert pending.state_hash == oidc.hash_state(state)
    assert pending.consumed_at is None

    callback = client.get(
        f"/api/v1/auth/oidc/callback?code=code-1&state={state}",
        follow_redirects=False,
    )

    assert callback.status_code == 302
    assert callback.headers["location"] == "/"
    cookies = callback.headers.get_list("set-cookie")
    assert any(oidc_settings.auth_access_cookie in value for value in cookies)
    assert any("HttpOnly" in value for value in cookies)

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == CUSTOMER_EMAIL

    assert idp.verifiers_seen["code-1"] == pending.code_verifier
    binding = db_session.scalar(select(UserIdentity))
    assert binding is not None
    assert binding.subject == SUBJECT
    assert binding.issuer == ISSUER
    audit = db_session.scalar(
        select(AuditEvent).where(AuditEvent.reason_code == "oidc_login")
    )
    assert audit is not None

    db_session.expire_all()
    consumed = db_session.scalar(select(OidcLoginRequest))
    assert consumed is not None
    assert consumed.consumed_at is not None


def test_authorization_code_flow_rejects_state_replay(
    client: TestClient,
    idp: FakeIdentityProvider,
    idp_http: httpx.Client,
    oidc_settings: Settings,
) -> None:
    _wire(client, idp_http)
    _, params = _start(client, idp)
    state = params["state"][0]

    first = client.get(
        f"/api/v1/auth/oidc/callback?code=code-1&state={state}", follow_redirects=False
    )
    assert first.status_code == 302

    replay = client.get(
        f"/api/v1/auth/oidc/callback?code=code-1&state={state}", follow_redirects=False
    )

    assert replay.status_code == 400
    assert replay.json()["error"]["code"] == "oidc_flow_failed"


def test_unknown_email_is_not_provisioned_implicitly(
    client: TestClient,
    db_session: Session,
    idp: FakeIdentityProvider,
    idp_http: httpx.Client,
    oidc_settings: Settings,
) -> None:
    _wire(client, idp_http)
    idp.email = "stranger@example.com"  # type: ignore[attr-defined]
    original = idp.id_token

    def token_with_stranger_email() -> str:
        return original(email="stranger@example.com")

    idp.id_token = token_with_stranger_email  # type: ignore[method-assign]
    _, params = _start(client, idp)

    response = client.get(
        f"/api/v1/auth/oidc/callback?code=code-2&state={params['state'][0]}",
        follow_redirects=False,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "oidc_account_not_linked"
    assert db_session.scalar(select(UserIdentity)) is None


def test_provider_endpoint_advertises_oidc_only_when_enabled(
    client: TestClient,
    oidc_settings: Settings,
) -> None:
    enabled = client.get("/api/v1/auth/providers")

    assert enabled.status_code == 200
    assert enabled.json()["password"] is True
    assert enabled.json()["oidc"]["enabled"] is True
    assert enabled.json()["oidc"]["display_name"]


def test_provider_endpoint_reports_oidc_disabled_by_default(client: TestClient) -> None:
    response = client.get("/api/v1/auth/providers")

    assert response.status_code == 200
    assert response.json()["oidc"]["enabled"] is False


@pytest.mark.parametrize(
    "case",
    [
        "wrong_nonce",
        "wrong_audience",
        "expired",
        "unverified_email",
        "tampered",
        "unknown_kid",
        "symmetric_algorithm",
    ],
)
def test_id_token_verification_rejects_invalid_tokens(
    idp: FakeIdentityProvider,
    idp_http: httpx.Client,
    oidc_settings: Settings,
    case: str,
) -> None:
    metadata = oidc.fetch_metadata(oidc_settings, client=idp_http)
    nonce = "expected-nonce"
    token = idp.id_token(nonce=nonce)

    if case == "wrong_nonce":
        token = idp.id_token(nonce="other-nonce")
    elif case == "wrong_audience":
        token = idp.id_token(nonce=nonce, audience="another-client")
    elif case == "expired":
        token = idp.id_token(nonce=nonce, expires_in=-60)
    elif case == "unverified_email":
        token = idp.id_token(nonce=nonce, email_verified=False)
    elif case == "tampered":
        header, payload, signature = token.split(".")
        token = f"{header}.{payload[:-2]}xx.{signature}"
    elif case == "unknown_kid":
        token = idp.id_token(nonce=nonce, kid="rotated-key")
    elif case == "symmetric_algorithm":
        token = idp.id_token(
            nonce=nonce, algorithm="HS256", signing_key=idp.public_secret_lookalike()
        )

    with pytest.raises(oidc.OidcFlowError):
        oidc.verify_id_token(
            oidc_settings, metadata, token, nonce=nonce, client=idp_http
        )


def test_id_token_verification_accepts_a_valid_token(
    idp: FakeIdentityProvider,
    idp_http: httpx.Client,
    oidc_settings: Settings,
) -> None:
    metadata = oidc.fetch_metadata(oidc_settings, client=idp_http)

    identity = oidc.verify_id_token(
        oidc_settings,
        metadata,
        idp.id_token(nonce="nonce-1", email="Beta.Developer@Example.com"),
        nonce="nonce-1",
        client=idp_http,
    )

    assert identity.subject == SUBJECT
    assert identity.email == CUSTOMER_EMAIL
    assert identity.display_name == "Beta Developer"
