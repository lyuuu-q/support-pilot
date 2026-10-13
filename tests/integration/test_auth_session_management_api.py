from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from support_pilot.config import get_settings
from support_pilot.infrastructure.models import AuditEvent, AuthSession

DEMO_PASSWORD = "SupportPilotDemo!2026"
CUSTOMER_EMAIL = "beta.developer@example.com"
SUPPORT_EMAIL = "support.agent@example.com"


def _login(client: TestClient, email: str = CUSTOMER_EMAIL) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": DEMO_PASSWORD},
    )
    assert response.status_code == 200


def _csrf_headers(client: TestClient) -> dict[str, str]:
    cookie = client.cookies.get(get_settings().auth_csrf_cookie)
    assert cookie
    return {get_settings().auth_csrf_header: cookie}


def _replace_cookie(client: TestClient, name: str, value: str, *, path: str = "/") -> None:
    client.cookies.set(name, value, path=path)


def test_list_sessions_marks_the_current_browser_session(client: TestClient) -> None:
    _login(client)
    _login(client)

    response = client.get("/api/v1/auth/sessions")

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2
    assert sum(1 for item in items if item["current"]) == 1
    assert all("csrf" not in item for item in items)


def test_revoke_one_session_keeps_the_current_session_working(
    client: TestClient,
    db_session: Session,
) -> None:
    _login(client)
    settings = get_settings()
    first_access = client.cookies.get(settings.auth_access_cookie)
    _login(client)
    sessions = client.get("/api/v1/auth/sessions").json()["items"]
    stale = next(item for item in sessions if not item["current"])

    response = client.post(
        f"/api/v1/auth/sessions/{stale['id']}/revoke", headers=_csrf_headers(client)
    )

    assert response.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 200

    remaining = client.get("/api/v1/auth/sessions").json()["items"]
    assert [item["current"] for item in remaining] == [True]

    row = db_session.get(AuthSession, stale["id"])
    assert row is not None
    assert row.status == "revoked"
    assert row.revoked_at is not None

    client.cookies.clear()
    _replace_cookie(client, settings.auth_access_cookie, first_access or "")
    assert client.get("/api/v1/auth/me").status_code == 401

    audit = db_session.scalar(
        select(AuditEvent)
        .where(AuditEvent.reason_code == "session_revoked_by_owner")
        .order_by(AuditEvent.created_at.desc())
    )
    assert audit is not None


def test_cannot_revoke_another_users_session(client: TestClient) -> None:
    _login(client)
    victim = client.get("/api/v1/auth/sessions").json()["items"][0]["id"]
    _login(client, SUPPORT_EMAIL)

    response = client.post(
        f"/api/v1/auth/sessions/{victim}/revoke",
        headers=_csrf_headers(client),
    )

    assert response.status_code == 404
    assert client.get("/api/v1/auth/me").status_code == 200


def test_session_revocation_requires_csrf_header(client: TestClient) -> None:
    _login(client)
    target = client.get("/api/v1/auth/sessions").json()["items"][0]["id"]

    blocked = client.post(f"/api/v1/auth/sessions/{target}/revoke")

    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "csrf_token_invalid"


def test_logout_all_revokes_every_session_and_clears_cookies(
    client: TestClient,
    db_session: Session,
) -> None:
    _login(client)
    _login(client)
    settings = get_settings()
    first_access = client.cookies.get(settings.auth_access_cookie)

    response = client.post("/api/v1/auth/logout-all", headers=_csrf_headers(client))

    assert response.status_code == 204
    assert client.cookies.get(settings.auth_access_cookie) in (None, "")

    rows = list(db_session.scalars(select(AuthSession)))
    assert rows and all(row.status == "revoked" for row in rows)

    client.cookies.clear()
    _replace_cookie(client, settings.auth_access_cookie, first_access or "")
    assert client.get("/api/v1/auth/me").status_code == 401

    audit = db_session.scalar(
        select(AuditEvent)
        .where(AuditEvent.action == "auth.session.revoke_all")
        .order_by(AuditEvent.created_at.desc())
    )
    assert audit is not None
    assert audit.reason_code == "all_sessions_revoked"
