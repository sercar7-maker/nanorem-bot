from decimal import Decimal

import pytest

from database.models import Partner, Withdrawal, WithdrawalStatus
from database.models_balance import Balance, BalanceTransaction
from services.withdrawal_service import WithdrawalService


@pytest.fixture
def funded(isolated_database):
    with isolated_database() as session:
        partner = Partner(first_name="Withdrawal safety")
        session.add(partner)
        session.flush()
        partner_id = partner.id
        session.add(Balance(partner_id=partner_id,
                            amount=Decimal("100.00"), hold=Decimal("0.00")))
        session.commit()
        yield session, partner_id


@pytest.mark.parametrize("value", [
    "0", "-1", "NaN", "sNaN", "Infinity", "-Infinity", "0.001",
    "10000000000000000.00", "invalid",
])
def test_invalid_amount_does_not_write(funded, value):
    session, partner_id = funded
    with pytest.raises(ValueError):
        WithdrawalService(session).create_pending(partner_id, value)
    session.commit()
    assert session.query(Withdrawal).count() == 0
    assert session.query(BalanceTransaction).count() == 0
    balance = session.get(Balance, partner_id)
    assert balance.amount == Decimal("100.00")
    assert balance.hold == Decimal("0.00")


def test_insufficient_funds_leaves_no_request(funded):
    session, partner_id = funded
    with pytest.raises(ValueError):
        WithdrawalService(session).create_pending(partner_id, Decimal("100.01"))
    session.commit()
    assert session.query(Withdrawal).count() == 0
    assert session.query(BalanceTransaction).count() == 0
    assert session.get(Balance, partner_id).amount == Decimal("100.00")


@pytest.mark.parametrize("operation", ["create", "complete", "reject"])
def test_failure_after_balance_write_rolls_back_operation(
    funded, monkeypatch, operation,
):
    session, partner_id = funded
    service = WithdrawalService(session)
    withdrawal_id = None
    if operation != "create":
        withdrawal_id = service.create_pending(partner_id, Decimal("30.00")).id
        session.commit()
    before = (
        session.get(Balance, partner_id).amount,
        session.get(Balance, partner_id).hold,
        session.query(BalanceTransaction).count(),
    )
    method_name = {
        "create": "hold_funds",
        "complete": "confirm_hold_spent",
        "reject": "release_hold",
    }[operation]
    original = getattr(service.balance_service, method_name)

    def fail_after_write(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Injected failure")

    monkeypatch.setattr(service.balance_service, method_name, fail_after_write)
    with pytest.raises(RuntimeError, match="Injected failure"):
        if operation == "create":
            service.create_pending(partner_id, Decimal("30.00"))
        elif operation == "complete":
            service.complete(withdrawal_id)
        else:
            service.reject(withdrawal_id, "Test rejection")
    session.commit()
    session.expire_all()
    after = (
        session.get(Balance, partner_id).amount,
        session.get(Balance, partner_id).hold,
        session.query(BalanceTransaction).count(),
    )
    assert after == before
    if withdrawal_id is None:
        assert session.query(Withdrawal).count() == 0
    else:
        withdrawal = session.get(Withdrawal, withdrawal_id)
        assert withdrawal.status == WithdrawalStatus.PENDING
        assert withdrawal.processed_at is None
        assert withdrawal.admin_comment is None


@pytest.mark.parametrize("first,second", [
    ("complete", "complete"), ("complete", "reject"),
    ("reject", "reject"), ("reject", "complete"),
])
def test_finalized_withdrawal_cannot_be_processed_again(funded, first, second):
    session, partner_id = funded
    service = WithdrawalService(session)
    withdrawal_id = service.create_pending(partner_id, Decimal("30.00")).id
    getattr(service, first)(withdrawal_id)
    session.commit()
    before = (
        session.get(Balance, partner_id).amount,
        session.get(Balance, partner_id).hold,
        session.query(BalanceTransaction).count(),
        session.get(Withdrawal, withdrawal_id).status,
    )
    with pytest.raises(ValueError):
        getattr(service, second)(withdrawal_id)
    session.commit()
    session.expire_all()
    assert before == (
        session.get(Balance, partner_id).amount,
        session.get(Balance, partner_id).hold,
        session.query(BalanceTransaction).count(),
        session.get(Withdrawal, withdrawal_id).status,
    )


def test_successful_create_can_be_rolled_back(funded):
    session, partner_id = funded
    session.begin()
    session.connection().exec_driver_sql("BEGIN")
    WithdrawalService(session).create_pending(partner_id, Decimal("30.00"))
    session.rollback()
    assert session.query(Withdrawal).count() == 0
    assert session.query(BalanceTransaction).count() == 0
    assert session.get(Balance, partner_id).amount == Decimal("100.00")
    assert session.get(Balance, partner_id).hold == Decimal("0.00")
