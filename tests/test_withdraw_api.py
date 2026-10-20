import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from database.db import get_db
from database.models import Partner, Withdrawal, WithdrawalStatus
from database.models_balance import Balance, BalanceTransaction
from main import app
from services.withdrawal_service import WithdrawalService
from web import order_handler


@pytest.fixture
def withdraw_api(isolated_database, monkeypatch):
    monkeypatch.setattr(order_handler, "DEBUG", True)
    monkeypatch.setattr(order_handler, "ADMIN_API_SECRET", "test-secret")

    def override_db():
        session = isolated_database()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    client.headers.update({"X-Admin-Secret": "test-secret"})
    try:
        yield client, isolated_database
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)


def seed(factory, amount="100.00"):
    with factory() as session:
        partner = Partner(first_name="Withdraw API")
        session.add(partner)
        session.flush()
        session.add(Balance(
            partner_id=partner.id,
            amount=Decimal(amount),
            hold=Decimal("0.00"),
        ))
        session.commit()
        return partner.id


def state(factory, partner_id):
    with factory() as session:
        balance = session.get(Balance, partner_id)
        withdrawals = (
            session.query(Withdrawal)
            .filter_by(partner_id=partner_id)
            .order_by(Withdrawal.id)
            .all()
        )
        transactions = session.query(BalanceTransaction).filter_by(
            partner_id=partner_id,
        ).count()
        return (
            balance.amount,
            balance.hold,
            [
                (
                    row.id,
                    row.status,
                    row.request_id,
                    Decimal(str(row.amount)),
                )
                for row in withdrawals
            ],
            transactions,
        )


def post_withdraw(client, partner_id, amount, request_id):
    params = {"partner_id": partner_id, "amount": str(amount)}
    if request_id is not None:
        params["request_id"] = request_id
    return client.post("/withdraw", params=params)


def test_create_returns_canonical_key_and_stored_amount(withdraw_api):
    client, factory = withdraw_api
    partner_id = seed(factory)
    key = uuid.uuid4()

    response = post_withdraw(client, partner_id, Decimal("10.10"), str(key).upper())

    assert response.status_code == 200
    body = response.json()
    with factory() as session:
        withdrawal = session.get(Withdrawal, body["withdrawal_id"])
        assert withdrawal.request_id == str(key)
        assert Decimal(str(withdrawal.amount)) == Decimal("10.10")
    assert body["status"] == WithdrawalStatus.PENDING.value
    assert body["request_id"] == str(key)
    assert Decimal(str(body["amount"])) == Decimal("10.10")
    assert state(factory, partner_id)[0:2] == (
        Decimal("89.90"),
        Decimal("10.10"),
    )
    assert state(factory, partner_id)[3] == 1


def test_repeat_after_commit_does_not_reserve_again(withdraw_api):
    client, factory = withdraw_api
    partner_id = seed(factory)
    key = str(uuid.uuid4())

    first = post_withdraw(client, partner_id, Decimal("15.00"), key)
    assert first.status_code == 200
    before = state(factory, partner_id)

    second = post_withdraw(client, partner_id, Decimal("15.00"), key)

    assert second.status_code == 200
    assert second.json()["withdrawal_id"] == first.json()["withdrawal_id"]
    assert second.json()["status"] == WithdrawalStatus.PENDING.value
    assert second.json()["request_id"] == key
    assert state(factory, partner_id) == before


def test_same_key_with_different_amount_conflicts(withdraw_api):
    client, factory = withdraw_api
    partner_id = seed(factory)
    key = str(uuid.uuid4())
    created = post_withdraw(client, partner_id, Decimal("10.00"), key)
    assert created.status_code == 200
    before = state(factory, partner_id)

    response = post_withdraw(client, partner_id, Decimal("10.01"), key)

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Withdrawal request conflicts with existing data",
    }
    assert "10.01" not in response.text
    assert state(factory, partner_id) == before


def test_missing_request_id_is_rejected(withdraw_api):
    client, factory = withdraw_api
    partner_id = seed(factory)
    before = state(factory, partner_id)

    response = post_withdraw(client, partner_id, Decimal("10.00"), None)

    assert response.status_code == 422
    assert state(factory, partner_id) == before


@pytest.mark.parametrize("request_id", [
    "",
    "   ",
    "not-a-uuid",
    str(uuid.uuid1()),
])
def test_invalid_request_id_is_bad_request(withdraw_api, request_id):
    client, factory = withdraw_api
    partner_id = seed(factory)
    before = state(factory, partner_id)

    response = post_withdraw(client, partner_id, Decimal("10.00"), request_id)

    assert response.status_code == 400
    assert state(factory, partner_id) == before


@pytest.mark.parametrize("operation", ["complete", "reject"])
def test_repeat_after_final_status_does_not_reserve_again(
    withdraw_api, operation,
):
    client, factory = withdraw_api
    partner_id = seed(factory)
    key = str(uuid.uuid4())
    created = post_withdraw(client, partner_id, Decimal("30.00"), key)
    assert created.status_code == 200
    withdrawal_id = created.json()["withdrawal_id"]

    with factory() as session:
        service = WithdrawalService(session)
        if operation == "complete":
            service.complete(withdrawal_id)
        else:
            service.reject(withdrawal_id, admin_comment="Manual review")
        session.commit()
    before = state(factory, partner_id)

    response = post_withdraw(client, partner_id, Decimal("30.00"), key)

    assert response.status_code == 200
    body = response.json()
    assert body["withdrawal_id"] == withdrawal_id
    assert body["request_id"] == key
    assert Decimal(str(body["amount"])) == Decimal("30.00")
    assert body["status"] == (
        WithdrawalStatus.COMPLETED.value
        if operation == "complete"
        else WithdrawalStatus.REJECTED.value
    )
    assert state(factory, partner_id) == before


def test_unexpected_error_hides_details_and_leaves_no_hold(
    withdraw_api, monkeypatch,
):
    client, factory = withdraw_api
    partner_id = seed(factory)
    before = state(factory, partner_id)
    real_create = WithdrawalService.create_pending

    def fail_after_reserve(self, *args, **kwargs):
        real_create(self, *args, **kwargs)
        raise RuntimeError("internal-ledger-detail")

    monkeypatch.setattr(WithdrawalService, "create_pending", fail_after_reserve)
    response = post_withdraw(
        client,
        partner_id,
        Decimal("10.00"),
        str(uuid.uuid4()),
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Withdrawal processing error"}
    assert "internal-ledger-detail" not in response.text
    assert state(factory, partner_id) == before
