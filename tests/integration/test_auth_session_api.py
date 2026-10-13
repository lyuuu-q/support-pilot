from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from support_pilot.config import get_settings
from support_pilot.infrastructure.models import AuditEvent, AuthSession

DEMO_PASSWORD = "SupportPilotDemo!2026"
CUSTOMER_EMAIL = "beta.developer@example.com"


def _login(client: TestClient, email: str = CUSTOMER_EMAIL) -> dict[str, object]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": DEMO_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()


def _csrf_headers(client: TestClient) -> dict[str, str]:
    settings = get_settings()
    cookie = client.cookies.get(settings.auth_csrf_cookie)
    assert cookie, "CSRF cookie must be readable by the browser"
    return {settings.auth_csrf_header: cookie}


def _replace_cookie(client: TestClient, name: str, value: str, *, path: str = "/") -> None:
    client.cookies.set(name, value, path=path)


def _set_cookie_headers(response) -> list[str]:
    return [value for name, value in response.headers.multi_items() if name.lower() == "set-cookie"]


def test_cookie_login_keeps_tokens_out_of_javascript_and_authenticates_requests(
    client: TestClient,
    db_session: Session,
) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": CUSTOMER_EMAIL, "password": DEMO_PASSWORD},
    )

    assert response.status_code == 200
    body = response.json()
    assert "access_token" not in body
    assert body["user"]["email"] == CUSTOMER_EMAIL
    assert body["csrf_token"]

    settings = get_settings()
    cookies = _set_cookie_headers(response)
    access_cookie = next(c for c in cookies if c.startswith(settings.auth_access_cookie + "="))
    refresh_cookie = next(c for c in cookies if c.startswith(settings.auth_refresh_cookie + "="))
    csrf_cookie = next(c for c in cookies if c.startswith(settings.auth_csrf_cookie + "="))
    assert "HttpOnly" in access_cookie
    assert "HttpOnly" in refresh_cookie
    assert "HttpOnly" not in csrf_cookie
    assert f"Path={settings.auth_refresh_cookie_path}" in refresh_cookie

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == CUSTOMER_EMAIL

    session_row = db_session.scalar(select(AuthSession))
    assert session_row is not None
    assert session_row.status == "active"
    assert body["csrf_token"] not in session_row.csrf_hash


def test_cookie_session_requires_csrf_header_for_writes(client: TestClient) -> None:
    _login(client)
    payload = {"message": "HTTP 429 响应里的 Retry-After 应该如何处理？"}

    blocked = client.post("/api/v1/agent/resolve", json=payload)
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "csrf_token_invalid"

    mismatched = client.post(
        "/api/v1/agent/resolve",
        json=payload,
        headers={"X-CSRF-Token": "not-the-issued-token"},
    )
    assert mismatched.status_code == 403

    allowed = client.post("/api/v1/agent/resolve", json=payload, headers=_csrf_headers(client))
    assert allowed.status_code == 200
    assert allowed.json()["outcome"]


def test_refresh_rotates_the_token_and_rejects_replay(client: TestClient) -> None:
    first = _login(client)
    settings = get_settings()
    original_refresh = client.cookies.get(settings.auth_refresh_cookie)
    original_csrf = str(first["csrf_token"])

    refreshed = client.post("/api/v1/auth/refresh", headers=_csrf_headers(client))

    assert refreshed.status_code == 200
    assert refreshed.json()["user"]["email"] == CUSTOMER_EMAIL
    assert client.cookies.get(settings.auth_refresh_cookie) != original_refresh
    assert client.cookies.get(settings.auth_csrf_cookie) != original_csrf

    rotated_access = client.cookies.get(settings.auth_access_cookie)
    rotated_csrf = str(refreshed.json()["csrf_token"])
    client.cookies.clear()
    _replace_cookie(
        client,
        settings.auth_refresh_cookie,
        original_refresh or "",
        path=settings.auth_refresh_cookie_path,
    )
    _replace_cookie(client, settings.auth_csrf_cookie, rotated_csrf)
    replay = client.post(
        "/api/v1/auth/refresh", headers={settings.auth_csrf_header: rotated_csrf}
    )
    assert replay.status_code == 401

    client.cookies.clear()
    _replace_cookie(client, settings.auth_access_cookie, rotated_access or "")
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200


def test_logout_revokes_the_session_and_clears_cookies(
    client: TestClient,
    db_session: Session,
) -> None:
    _login(client)
    settings = get_settings()
    access_cookie = client.cookies.get(settings.auth_access_cookie)
    refresh_cookie = client.cookies.get(settings.auth_refresh_cookie)

    response = client.post("/api/v1/auth/logout", headers=_csrf_headers(client))

    assert response.status_code == 204
    assert client.cookies.get(settings.auth_access_cookie) in (None, "")
    assert client.cookies.get(settings.auth_refresh_cookie) in (None, "")

    _replace_cookie(client, settings.auth_access_cookie, access_cookie or "")
    replayed = client.get("/api/v1/auth/me")
    assert replayed.status_code == 401

    revoked = db_session.scalar(select(AuthSession))
    assert revoked is not None
    assert revoked.status == "revoked"
    assert revoked.revoked_at is not None

    _replace_cookie(client, settings.auth_csrf_cookie, "stale-csrf-token")
    _replace_cookie(
        client,
        settings.auth_refresh_cookie,
        refresh_cookie or "",
        path=settings.auth_refresh_cookie_path,
    )
    refresh_again = client.post(
        "/api/v1/auth/refresh",
        headers={settings.auth_csrf_header: "stale-csrf-token"},
    )
    assert refresh_again.status_code == 401

    audit = db_session.scalar(
        select(AuditEvent)
        .where(AuditEvent.action == "auth.session.revoke")
        .order_by(AuditEvent.created_at.desc())
    )
    assert audit is not None
    assert audit.reason_code == "session_revoked"


def test_token_mode_still_issues_bearer_tokens_for_scripts(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": CUSTOMER_EMAIL, "password": DEMO_PASSWORD, "session_mode": "token"},
    )

    assert response.status_code == 200
    token = response.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert client.cookies.get(get_settings().auth_access_cookie) in (None, "")
