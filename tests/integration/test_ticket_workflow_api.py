from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from support_pilot.infrastructure.models import (
    AuditEvent,
    HumanFeedback,
    TicketTransition,
)

DEMO_PASSWORD = "SupportPilotDemo!2026"


def _token(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": DEMO_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _bearer(token: str, *, idempotency_key: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _create_agent_ticket(client: TestClient, customer_token: str) -> tuple[str, str]:
    session_id = str(uuid4())
    draft = client.post(
        "/api/v1/agent/resolve",
        headers=_bearer(customer_token),
        json={"session_id": session_id, "message": "问题无法解决，请创建工单。"},
    )
    assert draft.status_code == 200
    assert draft.json()["outcome"] == "needs_confirmation"
    confirmed = client.post(
        "/api/v1/agent/resolve",
        headers=_bearer(customer_token, idempotency_key=f"confirm-{session_id}"),
        json={
            "session_id": session_id,
            "message": "确认创建",
            "confirmation": "confirm_ticket",
        },
    )
    assert confirmed.status_code == 200
    return confirmed.json()["tool_result"]["ticket_id"], confirmed.json()["request_id"]


def test_customer_lists_only_own_tenant_and_cross_tenant_read_is_audited(
    client: TestClient,
    db_session: Session,
) -> None:
    beta_token = _token(client, "beta.developer@example.com")
    alpha_token = _token(client, "alpha.admin@example.com")
    ticket_id, _run_id = _create_agent_ticket(client, beta_token)

    own = client.get("/api/v1/tickets", headers=_bearer(beta_token))
    denied = client.get(f"/api/v1/tickets/{ticket_id}", headers=_bearer(alpha_token))

    assert own.status_code == 200
    assert own.json()["total"] == 1
    assert own.json()["items"][0]["id"] == ticket_id
    assert denied.status_code == 403
    audit = db_session.scalar(
        select(AuditEvent)
        .where(AuditEvent.action == "ticket.read", AuditEvent.outcome == "denied")
        .order_by(AuditEvent.created_at.desc())
    )
    assert audit is not None
    assert audit.reason_code == "tenant_access_denied"


def test_claim_requires_support_role_version_and_idempotency(
    client: TestClient,
    db_session: Session,
) -> None:
    customer_token = _token(client, "beta.developer@example.com")
    support_token = _token(client, "support.agent@example.com")
    ticket_id, _run_id = _create_agent_ticket(client, customer_token)

    customer_denied = client.post(
        f"/api/v1/tickets/{ticket_id}/claim",
        headers=_bearer(customer_token, idempotency_key="customer-claim"),
        json={"expected_version": 1},
    )
    missing_key = client.post(
        f"/api/v1/tickets/{ticket_id}/claim",
        headers=_bearer(support_token),
        json={"expected_version": 1},
    )
    headers = _bearer(support_token, idempotency_key="support-claim-1")
    claimed = client.post(
        f"/api/v1/tickets/{ticket_id}/claim",
        headers=headers,
        json={"expected_version": 1},
    )
    replay = client.post(
        f"/api/v1/tickets/{ticket_id}/claim",
        headers=headers,
        json={"expected_version": 1},
    )
    changed_payload = client.post(
        f"/api/v1/tickets/{ticket_id}/claim",
        headers=headers,
        json={"expected_version": 2},
    )

    assert customer_denied.status_code == 403
    assert missing_key.status_code == 400
    assert claimed.status_code == 200
    assert claimed.json()["status"] == "triaged"
    assert claimed.json()["version"] == 2
    assert claimed.json()["assignee_id"] is not None
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert changed_payload.status_code == 409
    assert db_session.scalar(select(func.count()).select_from(TicketTransition)) == 1


def test_ticket_state_machine_rejects_illegal_and_stale_transitions(
    client: TestClient,
    db_session: Session,
) -> None:
    customer_token = _token(client, "beta.developer@example.com")
    support_token = _token(client, "support.agent@example.com")
    ticket_id, _run_id = _create_agent_ticket(client, customer_token)
    claim = client.post(
        f"/api/v1/tickets/{ticket_id}/claim",
        headers=_bearer(support_token, idempotency_key="claim-state-machine"),
        json={"expected_version": 1},
    )
    assert claim.status_code == 200

    illegal = client.post(
        f"/api/v1/tickets/{ticket_id}/transitions",
        headers=_bearer(support_token, idempotency_key="illegal-close"),
        json={"to_status": "closed", "expected_version": 2, "reason": "直接关闭"},
    )
    valid = client.post(
        f"/api/v1/tickets/{ticket_id}/transitions",
        headers=_bearer(support_token, idempotency_key="start-work"),
        json={"to_status": "in_progress", "expected_version": 2, "reason": "开始排查"},
    )
    stale = client.post(
        f"/api/v1/tickets/{ticket_id}/transitions",
        headers=_bearer(support_token, idempotency_key="stale-resolve"),
        json={"to_status": "resolved", "expected_version": 2, "reason": "旧版本提交"},
    )

    assert illegal.status_code == 409
    assert illegal.json()["error"]["code"] == "invalid_ticket_transition"
    assert valid.status_code == 200
    assert valid.json()["status"] == "in_progress"
    assert valid.json()["version"] == 3
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "concurrency_conflict"
    assert db_session.scalar(select(func.count()).select_from(TicketTransition)) == 2
    denied_reasons = set(
        db_session.scalars(
            select(AuditEvent.reason_code).where(AuditEvent.action == "ticket.transition")
        )
    )
    assert {"invalid_ticket_transition", "ticket_version_conflict"} <= denied_reasons


def test_feedback_is_idempotent_redacted_and_not_published_as_knowledge(
    client: TestClient,
    db_session: Session,
) -> None:
    customer_token = _token(client, "beta.developer@example.com")
    support_token = _token(client, "support.agent@example.com")
    ticket_id, agent_run_id = _create_agent_ticket(client, customer_token)
    headers = _bearer(support_token, idempotency_key="feedback-1")
    payload = {
        "agent_run_id": agent_run_id,
        "disposition": "edited",
        "resolution_category": "authentication",
        "knowledge_gap": True,
        "comment": "客户误发 Bearer abcdefghijk，已人工修订。",
    }

    created = client.post(
        f"/api/v1/tickets/{ticket_id}/feedback",
        headers=headers,
        json=payload,
    )
    replay = client.post(
        f"/api/v1/tickets/{ticket_id}/feedback",
        headers=headers,
        json=payload,
    )
    duplicate_with_new_key = client.post(
        f"/api/v1/tickets/{ticket_id}/feedback",
        headers=_bearer(support_token, idempotency_key="feedback-2"),
        json=payload,
    )

    assert created.status_code == 200
    assert "abcdefghijk" not in created.json()["comment"]
    assert "[REDACTED]" in created.json()["comment"]
    assert replay.status_code == 200
    assert replay.json()["id"] == created.json()["id"]
    assert replay.json()["replayed"] is True
    assert duplicate_with_new_key.status_code == 409
    assert db_session.scalar(select(func.count()).select_from(HumanFeedback)) == 1


def test_concurrent_claim_with_same_key_has_one_transition(client: TestClient) -> None:
    customer_token = _token(client, "beta.developer@example.com")
    support_token = _token(client, "support.agent@example.com")
    ticket_id, _run_id = _create_agent_ticket(client, customer_token)
    headers = _bearer(support_token, idempotency_key="concurrent-claim")

    def claim(_index: int) -> Response:
        return client.post(
            f"/api/v1/tickets/{ticket_id}/claim",
            headers=headers,
            json={"expected_version": 1},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(claim, range(2)))

    assert [response.status_code for response in responses] == [200, 200]
    assert {response.json()["version"] for response in responses} == {2}
    assert sum(response.json()["replayed"] for response in responses) == 1


def test_ticket_queue_supports_cursor_search_and_status_filter(
    client: TestClient,
    db_session: Session,
) -> None:
    customer_token = _token(client, "beta.developer@example.com")
    support_token = _token(client, "support.agent@example.com")
    created_ids = {_create_agent_ticket(client, customer_token)[0] for _ in range(3)}
    headers = _bearer(support_token)

    first_page = client.get("/api/v1/tickets?limit=2", headers=headers)
    assert first_page.status_code == 200
    first_payload = first_page.json()
    assert first_payload["total"] == 3
    assert len(first_payload["items"]) == 2
    assert first_payload["next_cursor"]

    second_page = client.get(
        f"/api/v1/tickets?limit=2&cursor={first_payload['next_cursor']}",
        headers=headers,
    )
    second_payload = second_page.json()
    assert second_page.status_code == 200
    paged_ids = {item["id"] for item in first_payload["items"]} | {
        item["id"] for item in second_payload["items"]
    }
    assert paged_ids == created_ids
    assert second_payload["next_cursor"] is None

    searched_code = first_payload["items"][0]["public_code"]
    searched = client.get(f"/api/v1/tickets?q={searched_code}", headers=headers)
    assert searched.status_code == 200
    assert searched.json()["total"] == 1
    assert searched.json()["items"][0]["public_code"] == searched_code

    target = first_payload["items"][0]
    claimed = client.post(
        f"/api/v1/tickets/{target['id']}/claim",
        headers=_bearer(support_token, idempotency_key="page-claim"),
        json={"expected_version": target["version"]},
    )
    assert claimed.status_code == 200
    open_tickets = client.get("/api/v1/tickets?status=open", headers=headers)
    triaged_tickets = client.get("/api/v1/tickets?status=triaged", headers=headers)
    assert all(item["status"] == "open" for item in open_tickets.json()["items"])
    assert [item["id"] for item in triaged_tickets.json()["items"]] == [target["id"]]

    invalid_cursor = client.get("/api/v1/tickets?cursor=not-a-cursor", headers=headers)
    conflicting = client.get(
        f"/api/v1/tickets?cursor={first_payload['next_cursor']}&offset=1",
        headers=headers,
    )
    assert invalid_cursor.status_code == 400
    assert conflicting.status_code == 400
