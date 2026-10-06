from decimal import Decimal

import pytest
from sqlalchemy import Boolean, Numeric, create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.base import Base
from database.migrations import upgrade_schema
from database.models import Commission, Partner, Purchase
from database.models_balance import (
    Balance,
    BalanceTransaction,
    BalanceTransactionType,
)


@pytest.fixture
def schema_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(connection, record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_money_columns_use_numeric_types():
    assert isinstance(Purchase.__table__.c.amount.type, Numeric)
    assert isinstance(Commission.__table__.c.amount.type, Numeric)
    assert isinstance(Commission.__table__.c.rate.type, Numeric)
    assert isinstance(Partner.__table__.c.consent_given.type, Boolean)


def test_purchase_external_reference_is_unique(schema_session):
    partner = Partner(first_name="Unique ext ref")
    schema_session.add(partner)
    schema_session.flush()
    schema_session.add(
        Purchase(
            purchase_number="UNIQUE-EXT-1",
            ext_ref="woo-unique-1",
            partner_id=partner.id,
            amount=Decimal("10.00"),
        )
    )
    schema_session.flush()
    schema_session.add(
        Purchase(
            purchase_number="UNIQUE-EXT-2",
            ext_ref="woo-unique-1",
            partner_id=partner.id,
            amount=Decimal("10.00"),
        )
    )

    with pytest.raises(IntegrityError):
        schema_session.flush()


def test_partner_and_purchase_foreign_keys_are_enforced(schema_session):
    schema_session.add(
        Purchase(
            purchase_number="ORPHAN-PURCHASE",
            partner_id=999999,
            amount=Decimal("10.00"),
        )
    )

    with pytest.raises(IntegrityError):
        schema_session.flush()


def test_commission_is_unique_per_purchase_level(schema_session):
    buyer = Partner(first_name="Unique commission buyer")
    recipient = Partner(first_name="Unique commission recipient")
    schema_session.add_all([buyer, recipient])
    schema_session.flush()
    purchase = Purchase(
        purchase_number="UNIQUE-COMMISSION-1",
        partner_id=buyer.id,
        amount=Decimal("100.00"),
    )
    schema_session.add(purchase)
    schema_session.flush()

    def commission():
        return Commission(
            partner_id=recipient.id,
            purchase_id=purchase.id,
            source_partner_id=buyer.id,
            level=1,
            rate=Decimal("0.20"),
            base_amount=Decimal("100.00"),
            amount=Decimal("20.00"),
        )

    schema_session.add(commission())
    schema_session.flush()
    schema_session.add(commission())

    with pytest.raises(IntegrityError):
        schema_session.flush()


def test_commission_balance_credit_reference_is_unique(schema_session):
    partner = Partner(first_name="Unique balance credit")
    schema_session.add(partner)
    schema_session.flush()
    schema_session.add(
        Balance(partner_id=partner.id, amount=Decimal("10.00"))
    )
    schema_session.flush()

    def transaction():
        return BalanceTransaction(
            partner_id=partner.id,
            amount=Decimal("10.00"),
            type=BalanceTransactionType.COMMISSION,
            reference_id=900001,
        )

    schema_session.add(transaction())
    schema_session.flush()
    schema_session.add(transaction())

    with pytest.raises(IntegrityError):
        schema_session.flush()


def test_legacy_schema_upgrade_is_idempotent():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE partners (id INTEGER PRIMARY KEY)"))
        connection.execute(
            text(
                "CREATE TABLE purchases "
                "(id INTEGER PRIMARY KEY, ext_ref VARCHAR(100))"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE commissions "
                "(id INTEGER PRIMARY KEY, purchase_id INTEGER, level INTEGER)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE balance_transactions "
                "(id INTEGER PRIMARY KEY, partner_id INTEGER, "
                "reference_id INTEGER, type VARCHAR(30))"
            )
        )

    upgrade_schema(engine)
    upgrade_schema(engine)

    inspector = inspect(engine)
    partner_columns = {
        column["name"] for column in inspector.get_columns("partners")
    }
    assert {
        "consent_given",
        "consent_version",
        "consent_date",
    }.issubset(partner_columns)
    assert any(
        index["name"] == "uq_purchases_ext_ref"
        for index in inspector.get_indexes("purchases")
    )
    assert any(
        index["name"] == "uq_commissions_purchase_level"
        for index in inspector.get_indexes("commissions")
    )
    assert any(
        index["name"] == "uq_balance_tx_commission_reference"
        for index in inspector.get_indexes("balance_transactions")
    )

    engine.dispose()
