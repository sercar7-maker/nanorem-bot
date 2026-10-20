import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event

from database.models import (
    AuthSession,
    Partner,
    PartnerStatus,
    Withdrawal,
    WithdrawalStatus,
)
from database.models_balance import Balance, BalanceTransaction
from web import auth_api
from web.admin_api import router as admin_router
from web.withdrawal_api import router as withdrawal_router

OWN_FIELDS = {
    "withdrawal_id",
    "amount",
    "status",
    "method",
    "created_at",
    "processed_at",
}
QUEUE_FIELDS = OWN_FIELDS | {"partner_id", "first_name", "last_name"}
SECRET_CARD = "4111111111111111"
SECRET_EMAIL = "hidden-payout@example.test"


def add_partner(
    factory,
    *,
    first_name,
    last_name="Owner",
    role="partner",
    root=False,
    allowed=False,
    email=None,
):
    session = factory()
    partner = Partner(
        first_name=first_name,
        last_name=last_name,
        email=email or f"{first_name}@example.test",
        phone="+15550004001",
        telegram_id=f"tg-{first_name}",
        role=role,
        status=PartnerStatus.ACTIVE,
        lineage=[],
        can_process_withdrawals=allowed,
    )
    session.add(partner)
    session.flush()
    if root:
        partner.root_id = partner.id
        partner.upline_id = None
    session.add(Balance(
        partner_id=partner.id,
        amount="100.00",
        hold="0.00",
    ))
    session.commit()
    partner_id = partner.id
    session.close()
    return partner_id


def add_withdrawal(
    factory,
    partner_id,
    amount,
    status=WithdrawalStatus.PENDING,
    *,
    method="manual",
    created_at=None,
    processed_at=None,
    details=None,
):
    session = factory()
    row = Withdrawal(
        partner_id=partner_id,
        amount=amount,
        method=method,
        details=details if details is not None else {
            "card": SECRET_CARD,
            "email": SECRET_EMAIL,
        },
        status=status,
        request_id=str(uuid.uuid4()),
        created_at=created_at,
        processed_at=processed_at,
        admin_comment="internal review note",
    )
    session.add(row)
    session.commit()
    withdrawal_id = row.id
    session.close()
    return withdrawal_id


def store_session(factory, partner_id, *, expired=False, revoked=False):
    token = (
        f"withdrawal-list-{partner_id}-{expired}-{revoked}-"
        f"{uuid.uuid4()}"
    )
    now = datetime.now(timezone.utc)
    session = factory()
    session.add(AuthSession(
        partner_id=partner_id,
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        expires_at=now + timedelta(days=-1 if expired else 1),
        revoked_at=now if revoked else None,
    ))
    session.commit()
    session.close()
    return token


def snapshot(factory):
    session = factory()
    try:
        withdrawals = [
            (
                row.id,
                str(row.amount),
                row.status,
                row.processed_at,
                row.admin_comment,
            )
            for row in session.query(Withdrawal).order_by(Withdrawal.id)
        ]
        balances = [
            (row.partner_id, str(row.amount), str(row.hold))
            for row in session.query(Balance).order_by(Balance.partner_id)
        ]
        transactions = session.query(BalanceTransaction).count()
        return withdrawals, balances, transactions
    finally:
        session.close()


@pytest.fixture
def lists_client(isolated_database, monkeypatch):
    monkeypatch.setattr(auth_api, "SessionLocal", isolated_database)
    application = FastAPI()
    application.include_router(withdrawal_router)
    application.include_router(admin_router)
    client = TestClient(application)
    try:
        yield client, isolated_database
    finally:
        client.close()


def authed(client, factory, partner_id, **session_flags):
    client.cookies.set(
        auth_api.SESSION_COOKIE_NAME,
        store_session(factory, partner_id, **session_flags),
    )


def test_lists_require_a_session(lists_client):
    client, _ = lists_client
    for path in ("/auth/me/withdrawals", "/auth/withdrawals/queue"):
        response = client.get(path)
        assert response.status_code == 401
        assert response.json()["detail"] == "Authentication required"


@pytest.mark.parametrize(("expired", "revoked"), [(True, False), (False, True)])
def test_unusable_session_cannot_read_lists(lists_client, expired, revoked):
    client, factory = lists_client
    partner_id = add_partner(factory, first_name="Closed", allowed=True)
    add_withdrawal(factory, partner_id, "10.00")
    authed(client, factory, partner_id, expired=expired, revoked=revoked)

    for path in ("/auth/me/withdrawals", "/auth/withdrawals/queue"):
        response = client.get(path)
        assert response.status_code == 401


def test_partner_sees_only_own_withdrawals(lists_client):
    client, factory = lists_client
    owner = add_partner(factory, first_name="Owner", last_name="One")
    other = add_partner(factory, first_name="Other", last_name="Two")
    own_id = add_withdrawal(
        factory,
        owner,
        "10.10",
        created_at=datetime(2026, 1, 2, 10, 0, 0),
    )
    add_withdrawal(
        factory,
        other,
        "99.99",
        created_at=datetime(2026, 2, 2, 10, 0, 0),
    )
    completed = add_withdrawal(
        factory,
        owner,
        "0.29",
        WithdrawalStatus.COMPLETED,
        created_at=datetime(2026, 1, 1, 10, 0, 0),
        processed_at=datetime(2026, 1, 3, 10, 0, 0),
    )
    authed(client, factory, owner)
    before = snapshot(factory)

    response = client.get(
        "/auth/me/withdrawals",
        params={"partner_id": other, "limit": 1},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert set(body) == {"items", "limit", "offset"}
    assert body["limit"] == 1
    assert body["offset"] == 0
    assert [item["withdrawal_id"] for item in body["items"]] == [own_id]
    assert set(body["items"][0]) == OWN_FIELDS
    assert body["items"][0]["amount"] == "10.10"
    assert body["items"][0]["status"] == "pending"
    assert SECRET_CARD not in response.text
    assert SECRET_EMAIL not in response.text
    assert "internal review note" not in response.text
    assert "99.99" not in response.text
    assert completed not in [
        item["withdrawal_id"] for item in body["items"]
    ]
    assert snapshot(factory) == before


def test_own_list_includes_every_status_without_processing_permission(
    lists_client,
):
    client, factory = lists_client
    owner = add_partner(factory, first_name="Plain", allowed=False)
    pending = add_withdrawal(
        factory, owner, "1.00", created_at=datetime(2026, 1, 2),
    )
    completed = add_withdrawal(
        factory,
        owner,
        "2.00",
        WithdrawalStatus.COMPLETED,
        created_at=datetime(2026, 1, 3),
        processed_at=datetime(2026, 1, 4),
    )
    authed(client, factory, owner)

    response = client.get("/auth/me/withdrawals")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert [item["withdrawal_id"] for item in response.json()["items"]] == [
        completed,
        pending,
    ]
    assert response.json()["limit"] == 20
    assert response.json()["offset"] == 0


def test_own_status_filter_pagination_and_sort(lists_client):
    client, factory = lists_client
    owner = add_partner(factory, first_name="Sorted")
    same_time = datetime(2026, 3, 1, 12, 0, 0)
    older = add_withdrawal(
        factory, owner, "3.00", created_at=datetime(2026, 1, 1),
    )
    lower_id = add_withdrawal(factory, owner, "4.00", created_at=same_time)
    higher_id = add_withdrawal(factory, owner, "5.50", created_at=same_time)
    add_withdrawal(
        factory,
        owner,
        "6.00",
        WithdrawalStatus.REJECTED,
        created_at=datetime(2026, 4, 1),
    )
    authed(client, factory, owner)

    page = client.get(
        "/auth/me/withdrawals",
        params={"status": "pending", "limit": 2, "offset": 1},
    )

    assert page.status_code == 200
    assert [item["withdrawal_id"] for item in page.json()["items"]] == [
        lower_id,
        older,
    ]
    assert higher_id > lower_id
    assert page.json()["items"][0]["amount"] == "4.00"
    empty = client.get(
        "/auth/me/withdrawals",
        params={"status": "completed"},
    )
    assert empty.status_code == 200
    assert empty.json()["items"] == []
    assert empty.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("params", [
    {"status": "paid"},
    {"limit": 0},
    {"limit": 101},
    {"offset": -1},
])
def test_invalid_list_query_is_unprocessable(lists_client, params):
    client, factory = lists_client
    owner = add_partner(
        factory,
        first_name="Invalid query",
        allowed=True,
    )
    authed(client, factory, owner)
    for path in ("/auth/me/withdrawals", "/auth/withdrawals/queue"):
        response = client.get(path, params=params)
        assert response.status_code == 422


@pytest.mark.parametrize("kind", ["partner", "root", "admin"])
def test_queue_rejects_authenticated_users_without_permission(
    lists_client, kind,
):
    client, factory = lists_client
    partner_id = add_partner(
        factory,
        first_name=f"Queue {kind}",
        role="admin" if kind == "admin" else "partner",
        root=kind == "root",
        allowed=False,
    )
    authed(client, factory, partner_id)
    response = client.get("/auth/withdrawals/queue")
    assert response.status_code == 403
    assert response.json()["detail"] == "Withdrawal processing is not allowed"


def test_queue_shows_pending_rows_for_every_owner(lists_client):
    client, factory = lists_client
    processor = add_partner(
        factory,
        first_name="Processor",
        last_name="Companion",
        role="partner",
        allowed=True,
    )
    first = add_partner(factory, first_name="Ada", last_name="Lovelace")
    second = add_partner(factory, first_name="Grace", last_name=None)
    pending_first = add_withdrawal(
        factory, first, "10.10", created_at=datetime(2026, 5, 2),
    )
    pending_second = add_withdrawal(
        factory, second, "0.29", created_at=datetime(2026, 5, 1),
    )
    add_withdrawal(
        factory,
        first,
        "8.00",
        WithdrawalStatus.COMPLETED,
        created_at=datetime(2026, 6, 1),
        processed_at=datetime(2026, 6, 2),
    )
    authed(client, factory, processor)
    before = snapshot(factory)

    response = client.get("/auth/withdrawals/queue")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert [item["withdrawal_id"] for item in body["items"]] == [
        pending_first,
        pending_second,
    ]
    assert set(body["items"][0]) == QUEUE_FIELDS
    assert body["items"][0]["partner_id"] == first
    assert body["items"][0]["first_name"] == "Ada"
    assert body["items"][0]["last_name"] == "Lovelace"
    assert body["items"][0]["amount"] == "10.10"
    assert body["items"][1]["amount"] == "0.29"
    assert body["items"][1]["last_name"] is None
    assert SECRET_CARD not in response.text
    assert SECRET_EMAIL not in response.text
    assert "internal review note" not in response.text
    assert "can_process_withdrawals" not in response.text
    assert snapshot(factory) == before
    assert client.get("/admin/partners").status_code == 403


def test_queue_filter_and_revoked_permission(lists_client):
    client, factory = lists_client
    processor = add_partner(
        factory, first_name="Temporary", allowed=True,
    )
    owner = add_partner(factory, first_name="Payee", last_name="Person")
    add_withdrawal(factory, owner, "7.00")
    completed = add_withdrawal(
        factory,
        owner,
        "8.50",
        WithdrawalStatus.COMPLETED,
        processed_at=datetime(2026, 7, 1),
    )
    authed(client, factory, processor)

    filtered = client.get(
        "/auth/withdrawals/queue",
        params={"status": "completed"},
    )
    assert filtered.status_code == 200
    assert [item["withdrawal_id"] for item in filtered.json()["items"]] == [
        completed,
    ]
    assert filtered.json()["items"][0]["amount"] == "8.50"
    assert filtered.json()["items"][0]["processed_at"] is not None

    session = factory()
    session.get(Partner, processor).can_process_withdrawals = False
    session.commit()
    session.close()

    denied = client.get("/auth/withdrawals/queue")
    assert denied.status_code == 403


def test_queue_query_is_limited_in_the_database(lists_client):
    client, factory = lists_client
    processor = add_partner(factory, first_name="Limited", allowed=True)
    owners = [
        add_partner(factory, first_name=f"Payee {index}")
        for index in range(4)
    ]
    for index, owner in enumerate(owners):
        add_withdrawal(
            factory,
            owner,
            "1.00",
            created_at=datetime(2026, 8, index + 1),
        )
    authed(client, factory, processor)
    bound = factory()
    engine = bound.get_bind()
    bound.close()
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = client.get(
            "/auth/withdrawals/queue",
            params={"limit": 2},
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    assert response.status_code == 200
    assert len(response.json()["items"]) == 2
    queue_selects = [
        statement for statement in statements
        if "FROM withdrawals" in statement
    ]
    assert len(queue_selects) == 1
    assert "LIMIT" in queue_selects[0].upper()
    assert "partners.email" not in queue_selects[0]
    assert "partners.phone" not in queue_selects[0]
    assert "partners.telegram_id" not in queue_selects[0]
