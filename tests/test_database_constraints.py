from decimal import Decimal

import pytest
from sqlalchemy import (
    Boolean,
    Float,
    Numeric,
    create_engine,
    event,
    inspect,
    text,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from database.base import Base
from database.migrations import upgrade_schema
from database.models import Commission, Partner, Purchase, Withdrawal
from database.models_stats import PartnerStats
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
    monetary_columns = (
        Purchase.__table__.c.amount,
        Commission.__table__.c.rate,
        Commission.__table__.c.base_amount,
        Commission.__table__.c.amount,
        Withdrawal.__table__.c.amount,
        Balance.__table__.c.amount,
        Balance.__table__.c.hold,
        BalanceTransaction.__table__.c.amount,
        PartnerStats.__table__.c.personal_turnover,
        PartnerStats.__table__.c.network_turnover,
        PartnerStats.__table__.c.monthly_personal_turnover,
        PartnerStats.__table__.c.monthly_network_turnover,
    )
    assert all(isinstance(column.type, Numeric) for column in monetary_columns)
    assert isinstance(Partner.__table__.c.consent_given.type, Boolean)


def test_sqlite_numeric_amount_round_trips_as_decimal(schema_session):
    partner = Partner(first_name="Decimal round trip")
    schema_session.add(partner)
    schema_session.flush()
    purchase = Purchase(
        purchase_number="DECIMAL-ROUND-TRIP",
        partner_id=partner.id,
        amount=Decimal("0.29"),
    )
    schema_session.add(purchase)
    schema_session.commit()

    reloaded = schema_session.get(Purchase, purchase.id)

    assert reloaded.amount == Decimal("0.29")


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


def test_core_foreign_keys_exist_without_cascade(schema_session):
    inspector = inspect(schema_session.get_bind())
    expected = {
        "partners": {("upline_id", "partners", "id")},
        "purchases": {("partner_id", "partners", "id")},
        "commissions": {
            ("partner_id", "partners", "id"),
            ("purchase_id", "purchases", "id"),
            ("source_partner_id", "partners", "id"),
        },
        "balances": {("partner_id", "partners", "id")},
        "balance_transactions": {("partner_id", "balances", "partner_id")},
        "withdrawals": {("partner_id", "partners", "id")},
        "partner_stats": {("partner_id", "partners", "id")},
    }
    for table, expected_foreign_keys in expected.items():
        actual = set()
        for foreign_key in inspector.get_foreign_keys(table):
            actual.update(
                (
                    local_column,
                    foreign_key["referred_table"],
                    remote_column,
                )
                for local_column, remote_column in zip(
                    foreign_key["constrained_columns"],
                    foreign_key["referred_columns"],
                )
            )
            assert not foreign_key.get("options", {}).get("ondelete")
        assert expected_foreign_keys.issubset(actual)

    assert schema_session.execute(text("PRAGMA foreign_keys")).scalar_one() == 1


def test_commission_credit_index_compiles_for_postgresql():
    index = next(
        index
        for index in BalanceTransaction.__table__.indexes
        if index.name == "uq_balance_tx_commission_reference"
    )

    compiled = str(CreateIndex(index).compile(dialect=postgresql.dialect()))

    assert "CREATE UNIQUE INDEX uq_balance_tx_commission_reference" in compiled
    assert "WHERE type = 'COMMISSION' AND reference_id IS NOT NULL" in compiled


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


def test_legacy_schema_upgrade_adds_missing_model_unique_keys():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE partners "
                "(id INTEGER PRIMARY KEY, telegram_id VARCHAR, "
                "telegram_link_code VARCHAR)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE purchases "
                "(id INTEGER PRIMARY KEY, ext_ref VARCHAR(100), "
                "purchase_number VARCHAR(50))"
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
        connection.execute(
            text(
                "CREATE TABLE consent_versions "
                "(id INTEGER PRIMARY KEY, version VARCHAR(20))"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE users "
                "(id INTEGER PRIMARY KEY, email VARCHAR(255), phone VARCHAR(20))"
            )
        )

    upgrade_schema(engine)
    upgrade_schema(engine)

    inspector = inspect(engine)
    expected = {
        "partners": {
            ("telegram_id",),
            ("telegram_link_code",),
        },
        "purchases": {
            ("ext_ref",),
            ("purchase_number",),
        },
        "commissions": {("purchase_id", "level")},
        "consent_versions": {("version",)},
        "users": {("email",), ("phone",)},
    }
    for table, expected_keys in expected.items():
        actual_keys = {
            tuple(index["column_names"])
            for index in inspector.get_indexes(table)
            if index["unique"]
        }
        actual_keys.update(
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints(table)
        )
        assert expected_keys.issubset(actual_keys)

    transaction_index = next(
        index
        for index in inspector.get_indexes("balance_transactions")
        if index["name"] == "uq_balance_tx_commission_reference"
    )
    assert transaction_index["unique"] == 1
    assert tuple(transaction_index["column_names"]) == (
        "partner_id",
        "reference_id",
    )
    assert "COMMISSION" in str(
        transaction_index["dialect_options"]["sqlite_where"]
    )
    engine.dispose()


def test_migration_refuses_duplicates_without_deleting_rows():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE purchases "
                "(id INTEGER PRIMARY KEY, ext_ref VARCHAR(100))"
            )
        )
        connection.execute(
            text(
                "INSERT INTO purchases (ext_ref) VALUES "
                "('duplicate-order'), ('duplicate-order')"
            )
        )

    with pytest.raises(
        RuntimeError,
        match="duplicate rows exist.*GROUP BY ext_ref",
    ):
        upgrade_schema(engine)

    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT COUNT(*) FROM purchases")
        ).scalar_one() == 2
    engine.dispose()


def test_migration_rejects_wrong_index_using_required_name():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE balance_transactions "
                "(id INTEGER PRIMARY KEY, partner_id INTEGER, "
                "reference_id INTEGER, type VARCHAR(30))"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX uq_balance_tx_commission_reference "
                "ON balance_transactions (partner_id)"
            )
        )

    with pytest.raises(
        RuntimeError,
        match="exists but does not enforce the required unique key",
    ):
        upgrade_schema(engine)
    engine.dispose()


def test_sqlite_legacy_float_columns_are_diagnosed_but_not_altered(caplog):
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE purchases "
                "(id INTEGER PRIMARY KEY, ext_ref VARCHAR(100), amount FLOAT)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO purchases (ext_ref, amount) "
                "VALUES ('legacy-order', 12.34)"
            )
        )

    upgrade_schema(engine)

    column = next(
        column
        for column in inspect(engine).get_columns("purchases")
        if column["name"] == "amount"
    )
    assert isinstance(column["type"], Float)
    assert "legacy floating-point monetary column(s) amount" in caplog.text
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT amount FROM purchases WHERE ext_ref='legacy-order'")
        ).scalar_one() == 12.34
    engine.dispose()
