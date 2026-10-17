from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from database.models import Base, Partner, Withdrawal
from database.models_balance import Balance, BalanceTransaction
from services.withdrawal_service import WithdrawalService


@pytest.fixture
def withdrawal_file_db(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'outer-rollback.sqlite').as_posix()}",
        poolclass=NullPool,
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    try:
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine)
        with factory() as session:
            partner = Partner(first_name="Outer rollback diagnostic")
            session.add(partner)
            session.flush()
            partner_id = partner.id
            session.add(Balance(
                partner_id=partner_id,
                amount=Decimal("100.00"),
                hold=Decimal("0.00"),
            ))
            session.commit()
        yield factory, partner_id
    finally:
        engine.dispose()


def snapshot(factory, partner_id):
    with factory() as session:
        balance = session.get(Balance, partner_id)
        return {
            "available": balance.amount,
            "reserved": balance.hold,
            "withdrawals": [
                (row.id, row.amount, row.status.value,
                 row.processed_at, row.admin_comment)
                for row in session.query(Withdrawal).order_by(Withdrawal.id)
            ],
            "transactions": [
                (row.id, row.amount, row.type.value, row.reference_id)
                for row in session.query(BalanceTransaction).order_by(BalanceTransaction.id)
            ],
        }


@pytest.mark.parametrize("operation", ["create", "complete", "reject"])
def test_outer_rollback_without_explicit_begin(withdrawal_file_db, operation):
    factory, partner_id = withdrawal_file_db
    withdrawal_id = None
    if operation != "create":
        with factory() as setup:
            withdrawal_id = WithdrawalService(setup).create_pending(
                partner_id=partner_id,
                amount=Decimal("30.00"),
            ).id
            setup.commit()

    before = snapshot(factory, partner_id)
    with factory() as session:
        service = WithdrawalService(session)
        if operation == "create":
            service.create_pending(
                partner_id=partner_id,
                amount=Decimal("30.00"),
            )
        elif operation == "complete":
            service.complete(withdrawal_id)
        else:
            service.reject(withdrawal_id, admin_comment="Diagnostic rejection")
        session.rollback()

    assert snapshot(factory, partner_id) == before
