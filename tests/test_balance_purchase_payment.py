import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal
from threading import Barrier

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateIndex

from core.balance_service import BalanceService
from database.base import Base
from database.migrations import upgrade_schema
from database.models import Commission, Partner, Purchase
from database.models_balance import (
    Balance,
    BalanceOrderReservation,
    BalanceOrderReservationStatus,
    BalanceTransaction,
    BalanceTransactionType,
)
from services import order_processor
from services.order_processor import OrderProcessor
from services.partner_service import PartnerService


def _create_partner_with_balance(session, amount: Decimal) -> Partner:
    partner = Partner(first_name="Balance checkout partner")
    session.add(partner)
    session.flush()
    session.add(
        Balance(
            partner_id=partner.id,
            amount=amount,
            hold=Decimal("0.00"),
        )
    )
    session.flush()
    return partner


def _create_root_pair() -> tuple[int, int]:
    service = PartnerService()
    first = service.create_root(first_name="Balance test Root 1")
    second = service.create_root(first_name="Balance test Root 2")
    return first.id, second.id


@pytest.mark.parametrize(
    ("available", "order_total", "expected_reservation", "expected_balance"),
    [
        ("6000.00", "5000.00", "5000.00", "1000.00"),
        ("3000.00", "5000.00", "3000.00", "0.00"),
        ("5000.00", "5000.00", "5000.00", "0.00"),
        ("0.00", "5000.00", "0.00", "0.00"),
    ],
)
def test_purchase_reservation_uses_up_to_available_balance(
    isolated_database,
    available,
    order_total,
    expected_reservation,
    expected_balance,
):
    session = isolated_database()
    partner = _create_partner_with_balance(
        session,
        Decimal(available),
    )

    reservation = BalanceService(session).reserve_purchase(
        partner.id,
        "order-partial",
        Decimal(order_total),
    )

    balance = session.get(Balance, partner.id)
    transaction = (
        session.query(BalanceTransaction)
        .filter_by(
            partner_id=partner.id,
            type=BalanceTransactionType.PURCHASE_PAYMENT,
        )
        .one()
    )
    assert Decimal(str(reservation.amount)) == Decimal(expected_reservation)
    assert Decimal(str(balance.amount)) == Decimal(expected_balance)
    assert Decimal(str(balance.hold)) == Decimal(expected_reservation)
    assert transaction.amount == -Decimal(expected_reservation)
    session.close()


def test_repeat_reserve_is_idempotent(isolated_database):
    session = isolated_database()
    partner = _create_partner_with_balance(session, Decimal("3000.00"))
    service = BalanceService(session)

    first = service.reserve_purchase(
        partner.id,
        701,
        Decimal("5000.00"),
    )
    second = service.reserve_purchase(
        partner.id,
        "701",
        Decimal("5000.00"),
    )

    assert first.id == second.id
    assert Decimal(str(second.amount)) == Decimal("3000.00")
    assert Decimal(str(session.get(Balance, partner.id).amount)) == 0
    assert (
        session.query(BalanceTransaction)
        .filter_by(
            partner_id=partner.id,
            type=BalanceTransactionType.PURCHASE_PAYMENT,
        )
        .count()
        == 1
    )
    session.close()


def test_repeat_reserve_rejects_changed_order_details(isolated_database):
    session = isolated_database()
    partner = _create_partner_with_balance(session, Decimal("3000.00"))
    service = BalanceService(session)
    service.reserve_purchase(partner.id, "changed-order", Decimal("1000.00"))

    with pytest.raises(ValueError, match="different partner or order total"):
        service.reserve_purchase(
            partner.id,
            "changed-order",
            Decimal("1200.00"),
        )

    assert Decimal(str(session.get(Balance, partner.id).amount)) == (
        Decimal("2000.00")
    )
    session.close()


def test_purchase_order_total_requires_currency_precision(isolated_database):
    session = isolated_database()
    partner = _create_partner_with_balance(session, Decimal("10.00"))

    with pytest.raises(ValueError, match="at most 2 decimals"):
        BalanceService(session).reserve_purchase(
            partner.id,
            "fractional-cent",
            Decimal("1.001"),
        )

    assert session.query(BalanceOrderReservation).count() == 0
    session.close()


def test_confirm_and_release_repeats_are_safe(isolated_database):
    session = isolated_database()
    partner = _create_partner_with_balance(session, Decimal("100.00"))
    service = BalanceService(session)

    confirmed = service.reserve_purchase(
        partner.id,
        "confirmed-order",
        Decimal("60.00"),
    )
    assert service.confirm_purchase("confirmed-order").status == (
        BalanceOrderReservationStatus.CONFIRMED
    )
    assert service.confirm_purchase("confirmed-order").status == (
        BalanceOrderReservationStatus.CONFIRMED
    )
    balance = session.get(Balance, partner.id)
    assert Decimal(str(balance.amount)) == Decimal("40.00")
    assert Decimal(str(balance.hold)) == Decimal("0.00")
    assert (
        session.query(BalanceTransaction)
        .filter_by(
            reference_id=confirmed.id,
            external_id="wc-order:confirmed-order:confirm",
        )
        .count()
        == 1
    )

    released = service.reserve_purchase(
        partner.id,
        "released-order",
        Decimal("30.00"),
    )
    assert service.release_purchase("released-order").status == (
        BalanceOrderReservationStatus.RELEASED
    )
    assert service.release_purchase("released-order").status == (
        BalanceOrderReservationStatus.RELEASED
    )
    balance = session.get(Balance, partner.id)
    assert Decimal(str(balance.amount)) == Decimal("40.00")
    assert Decimal(str(balance.hold)) == Decimal("0.00")
    assert (
        session.query(BalanceTransaction)
        .filter_by(
            reference_id=released.id,
            external_id="wc-order:released-order:release",
        )
        .count()
        == 1
    )
    session.close()


def test_failed_work_after_reserve_rolls_back_reservation_and_hold(
    isolated_database,
):
    session = isolated_database()
    partner = _create_partner_with_balance(session, Decimal("100.00"))
    session.commit()

    BalanceService(session).reserve_purchase(
        partner.id,
        "rollback-order",
        Decimal("75.00"),
    )
    with pytest.raises(RuntimeError, match="injected downstream error"):
        raise RuntimeError("injected downstream error")
    session.rollback()

    balance = session.get(Balance, partner.id)
    assert Decimal(str(balance.amount)) == Decimal("100.00")
    assert Decimal(str(balance.hold)) == Decimal("0.00")
    assert (
        session.query(BalanceOrderReservation)
        .filter_by(order_id="rollback-order")
        .count()
        == 0
    )
    assert session.query(BalanceTransaction).count() == 0
    session.close()


def test_two_concurrent_orders_cannot_over_reserve(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'concurrent-balance.sqlite'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(connection, record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    upgrade_schema(engine)
    session_factory = sessionmaker(bind=engine)

    setup = session_factory()
    partner = _create_partner_with_balance(setup, Decimal("3000.00"))
    setup.commit()
    partner_id = partner.id
    setup.close()

    start = Barrier(2)

    def reserve(order_id: str) -> Decimal:
        session = session_factory()
        try:
            start.wait(timeout=5)
            result = BalanceService(session).reserve_purchase(
                partner_id,
                order_id,
                Decimal("2500.00"),
            )
            session.commit()
            return Decimal(str(result.amount))
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            amounts = list(
                executor.map(reserve, ("concurrent-1", "concurrent-2"))
            )

        check = session_factory()
        balance = check.get(Balance, partner_id)
        assert sum(amounts) == Decimal("3000.00")
        assert Decimal(str(balance.amount)) == Decimal("0.00")
        assert Decimal(str(balance.hold)) == Decimal("3000.00")
        assert min(amounts) == Decimal("500.00")
        check.close()
    finally:
        engine.dispose()


def test_order_webhook_confirms_once_and_commission_uses_full_order_total(
    isolated_database,
    monkeypatch,
):
    root_ids = _create_root_pair()
    session = isolated_database()
    ancestor = Partner(
        first_name="Commission ancestor",
        upline_id=root_ids[0],
        root_id=root_ids[0],
        lineage=[root_ids[0]],
        subscription_end_date=datetime.utcnow() + timedelta(days=365),
    )
    buyer = Partner(
        first_name="Balance buyer",
        email="balance-buyer@example.test",
        lineage=[],
    )
    session.add_all([ancestor, buyer])
    session.flush()
    buyer.upline_id = ancestor.id
    buyer.root_id = root_ids[0]
    buyer.lineage = [ancestor.id, root_ids[0]]
    session.add(
        Balance(
            partner_id=buyer.id,
            amount=Decimal("3000.00"),
            hold=Decimal("0.00"),
        )
    )
    reservation = BalanceService(session).reserve_purchase(
        buyer.id,
        702,
        Decimal("5000.00"),
    )
    buyer_id = buyer.id
    reservation_id = reservation.id
    session.commit()
    session.close()

    monkeypatch.setattr(order_processor, "SessionLocal", isolated_database)
    payload = {
        "id": 702,
        "customer_id": 33,
        "total": "5000.00",
        "status": "completed",
        "billing": {
            "email": "balance-buyer@example.test",
            "first_name": "Balance",
            "last_name": "Buyer",
            "phone": "+10000000033",
        },
    }
    processor = OrderProcessor()
    assert asyncio.run(processor.process_order_data(payload)) is True
    assert asyncio.run(processor.process_order_data(payload)) is True

    session = isolated_database()
    purchase = session.query(Purchase).filter_by(ext_ref="702").one()
    commission = session.query(Commission).filter_by(
        purchase_id=purchase.id
    ).one()
    reservation = session.get(BalanceOrderReservation, reservation_id)
    buyer_balance = session.get(Balance, buyer_id)
    payment_transactions = session.query(BalanceTransaction).filter_by(
        partner_id=buyer_id,
        type=BalanceTransactionType.PURCHASE_PAYMENT,
    ).all()

    assert purchase.amount == Decimal("5000.00")
    assert commission.base_amount == Decimal("5000.00")
    assert commission.amount == Decimal("1000.00")
    assert reservation.status == BalanceOrderReservationStatus.CONFIRMED
    assert Decimal(str(buyer_balance.amount)) == Decimal("0.00")
    assert Decimal(str(buyer_balance.hold)) == Decimal("0.00")
    assert len(payment_transactions) == 2
    assert sum(tx.amount for tx in payment_transactions) == Decimal("-3000.00")
    session.close()


def test_cancelled_order_webhook_releases_pending_reservation(
    isolated_database,
    monkeypatch,
):
    session = isolated_database()
    partner = _create_partner_with_balance(session, Decimal("80.00"))
    partner_id = partner.id
    BalanceService(session).reserve_purchase(
        partner.id,
        "cancel-me",
        Decimal("50.00"),
    )
    session.commit()
    session.close()

    monkeypatch.setattr(order_processor, "SessionLocal", isolated_database)
    success = asyncio.run(
        OrderProcessor().process_order_data(
            {"id": "cancel-me", "status": "cancelled"}
        )
    )
    assert asyncio.run(
        OrderProcessor().process_order_data(
            {"id": "cancel-me", "status": "cancelled"}
        )
    ) is True

    session = isolated_database()
    balance = session.get(Balance, partner_id)
    reservation = session.query(BalanceOrderReservation).filter_by(
        order_id="cancel-me"
    ).one()
    assert success is True
    assert reservation.status == BalanceOrderReservationStatus.RELEASED
    assert Decimal(str(balance.amount)) == Decimal("80.00")
    assert Decimal(str(balance.hold)) == Decimal("0.00")
    session.close()


def test_order_processing_failure_keeps_reservation_pending(
    isolated_database,
    monkeypatch,
):
    root_ids = _create_root_pair()
    session = isolated_database()
    buyer = Partner(
        first_name="Rollback balance buyer",
        email="rollback-balance@example.test",
        upline_id=root_ids[0],
        root_id=root_ids[0],
        lineage=[root_ids[0]],
    )
    session.add(buyer)
    session.flush()
    session.add(
        Balance(
            partner_id=buyer.id,
            amount=Decimal("300.00"),
            hold=Decimal("0.00"),
        )
    )
    BalanceService(session).reserve_purchase(
        buyer.id,
        "rollback-webhook",
        Decimal("500.00"),
    )
    buyer_id = buyer.id
    session.commit()
    session.close()

    class FailingCalculator:
        def __init__(self, db, bot):
            pass

        async def process_purchase(self, purchase):
            raise RuntimeError("injected commission failure")

    monkeypatch.setattr(order_processor, "SessionLocal", isolated_database)
    monkeypatch.setattr(
        order_processor,
        "CommissionCalculator",
        FailingCalculator,
    )
    success = asyncio.run(
        OrderProcessor().process_order_data(
            {
                "id": "rollback-webhook",
                "customer_id": 44,
                "total": "500.00",
                "status": "completed",
                "billing": {
                    "email": "rollback-balance@example.test",
                    "first_name": "Rollback",
                    "last_name": "Buyer",
                },
            }
        )
    )

    session = isolated_database()
    balance = session.get(Balance, buyer_id)
    reservation = session.query(BalanceOrderReservation).filter_by(
        order_id="rollback-webhook"
    ).one()
    assert success is False
    assert reservation.status == BalanceOrderReservationStatus.PENDING
    assert Decimal(str(balance.amount)) == Decimal("0.00")
    assert Decimal(str(balance.hold)) == Decimal("300.00")
    assert session.query(Purchase).filter_by(
        ext_ref="rollback-webhook"
    ).count() == 0
    assert session.query(BalanceTransaction).filter_by(
        external_id="wc-order:rollback-webhook:confirm"
    ).count() == 0
    session.close()


def test_purchase_ledger_idempotency_index_compiles_for_postgresql():
    index = next(
        index
        for index in BalanceTransaction.__table__.indexes
        if index.name == "uq_balance_tx_purchase_external_id"
    )
    compiled = str(
        CreateIndex(index).compile(dialect=postgresql.dialect())
    )

    assert "CREATE UNIQUE INDEX uq_balance_tx_purchase_external_id" in compiled
    assert (
        "WHERE type = 'PURCHASE_PAYMENT' AND external_id IS NOT NULL"
        in compiled
    )


@pytest.mark.parametrize(
    ("table_sql", "insert_sql", "count_sql", "message"),
    [
        (
            "CREATE TABLE balance_transactions "
            "(id INTEGER PRIMARY KEY, partner_id INTEGER, "
            "reference_id INTEGER, type VARCHAR(30), external_id VARCHAR)",
            "INSERT INTO balance_transactions "
            "(partner_id, reference_id, type, external_id) VALUES "
            "(1, 10, 'PURCHASE_PAYMENT', 'wc-order:10:reserve'), "
            "(1, 11, 'PURCHASE_PAYMENT', 'wc-order:10:reserve')",
            "SELECT COUNT(*) FROM balance_transactions",
            "duplicate rows exist.*balance_transactions",
        ),
        (
            "CREATE TABLE balance_order_reservations "
            "(id INTEGER PRIMARY KEY, order_id VARCHAR(100))",
            "INSERT INTO balance_order_reservations (order_id) VALUES "
            "('duplicate-order'), ('duplicate-order')",
            "SELECT COUNT(*) FROM balance_order_reservations",
            "duplicate rows exist.*balance_order_reservations",
        ),
    ],
)
def test_migration_stops_on_purchase_idempotency_duplicates(
    table_sql,
    insert_sql,
    count_sql,
    message,
):
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text(table_sql))
        connection.execute(text(insert_sql))

    with pytest.raises(RuntimeError, match=message):
        upgrade_schema(engine)

    with engine.connect() as connection:
        assert connection.execute(text(count_sql)).scalar_one() == 2
    engine.dispose()
