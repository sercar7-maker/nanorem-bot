import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from database.migrations import upgrade_schema
from database.models import Partner, Withdrawal, WithdrawalStatus
from database.models_balance import Balance, BalanceTransaction
from services.withdrawal_service import (
    WithdrawalRequestConflict,
    WithdrawalService,
)


def add_partner(session, amount="100.00", name="Request key"):
    partner = Partner(first_name=name)
    session.add(partner)
    session.flush()
    session.add(Balance(
        partner_id=partner.id,
        amount=Decimal(amount),
        hold=Decimal("0.00"),
    ))
    session.commit()
    return partner.id


def state(session, partner_id):
    session.expire_all()
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
            (row.id, row.status, row.request_id, Decimal(str(row.amount)))
            for row in withdrawals
        ],
        transactions,
    )


def test_repeat_with_same_key_and_data_does_not_reserve_again(
    isolated_database,
):
    with isolated_database() as session:
        partner_id = add_partner(session)
        service = WithdrawalService(session)
        key = str(uuid.uuid4())
        created = service.create_pending(
            partner_id,
            Decimal("15.50"),
            method="manual",
            details={"channel": "manual"},
            request_id=key,
        )
        session.commit()
        before = state(session, partner_id)

        again = service.create_pending(
            partner_id,
            Decimal("15.50"),
            method="manual",
            details={"channel": "manual"},
            request_id=key,
        )
        session.commit()

        assert again.id == created.id
        assert again.status == WithdrawalStatus.PENDING
        assert state(session, partner_id) == before


def test_equivalent_amount_and_uuid_reuse_the_same_withdrawal(
    isolated_database,
):
    with isolated_database() as session:
        partner_id = add_partner(session)
        service = WithdrawalService(session)
        key = uuid.uuid4()
        created = service.create_pending(
            partner_id,
            Decimal("10.10"),
            details={"b": 1, "a": {"d": 2, "c": 3}},
            request_id=str(key).upper(),
        )
        session.commit()
        before = state(session, partner_id)
        forms = [
            key,
            key.hex,
            "{" + str(key) + "}",
            "urn:uuid:" + str(key).upper(),
            "  " + str(key) + "\n",
        ]
        amounts = [
            Decimal("10.1"),
            "10.10",
            Decimal("10.10"),
            Decimal("10.10"),
            Decimal("10.10"),
        ]
        details = {"a": {"c": 3, "d": 2}, "b": 1}

        for request_id, amount in zip(forms, amounts):
            again = service.create_pending(
                partner_id,
                amount,
                request_id=request_id,
                details=details,
            )
            assert again.id == created.id

        session.commit()
        assert created.request_id == str(key)
        assert state(session, partner_id) == before


@pytest.mark.parametrize(("amount", "method", "details"), [
    (Decimal("10.01"), "manual", {"channel": "manual"}),
    (Decimal("10.00"), "bank", {"channel": "manual"}),
    (Decimal("10.00"), "manual", {"channel": "other"}),
    (Decimal("10.00"), "manual", {}),
])
def test_same_key_with_different_data_is_a_conflict(
    isolated_database, amount, method, details,
):
    with isolated_database() as session:
        partner_id = add_partner(session)
        service = WithdrawalService(session)
        key = str(uuid.uuid4())
        service.create_pending(
            partner_id,
            Decimal("10.00"),
            method="manual",
            details={"channel": "manual"},
            request_id=key,
        )
        session.commit()
        before = state(session, partner_id)

        with pytest.raises(WithdrawalRequestConflict):
            service.create_pending(
                partner_id,
                amount,
                method=method,
                details=details,
                request_id=key,
            )
        session.commit()
        assert state(session, partner_id) == before


def test_same_key_is_independent_for_each_partner(isolated_database):
    with isolated_database() as session:
        first_partner = add_partner(session, name="First partner")
        second_partner = add_partner(session, name="Second partner")
        service = WithdrawalService(session)
        key = str(uuid.uuid4())

        first = service.create_pending(
            first_partner, Decimal("10.00"), request_id=key,
        )
        second = service.create_pending(
            second_partner, Decimal("12.00"), request_id=key,
        )
        session.commit()

        assert first.id != second.id
        assert first.request_id == second.request_id == key
        assert state(session, first_partner)[0:2] == (
            Decimal("90.00"), Decimal("10.00"),
        )
        assert state(session, second_partner)[0:2] == (
            Decimal("88.00"), Decimal("12.00"),
        )


def test_different_keys_create_independent_withdrawals(isolated_database):
    with isolated_database() as session:
        partner_id = add_partner(session)
        service = WithdrawalService(session)
        first = service.create_pending(
            partner_id,
            Decimal("10.00"),
            request_id=str(uuid.uuid4()),
        )
        second = service.create_pending(
            partner_id,
            Decimal("20.00"),
            request_id=str(uuid.uuid4()),
        )
        session.commit()

        assert first.id != second.id
        assert first.request_id != second.request_id
        assert state(session, partner_id)[0:2] == (
            Decimal("70.00"), Decimal("30.00"),
        )
        assert state(session, partner_id)[3] == 2


def test_missing_request_id_creates_a_new_withdrawal(isolated_database):
    with isolated_database() as session:
        partner_id = add_partner(session)
        service = WithdrawalService(session)
        first = service.create_pending(partner_id, Decimal("10.00"))
        second = service.create_pending(
            partner_id,
            Decimal("10.00"),
            method="manual",
            details={},
        )
        session.commit()

        assert first.id != second.id
        assert first.request_id is None
        assert second.request_id is None
        assert state(session, partner_id)[0:2] == (
            Decimal("80.00"), Decimal("20.00"),
        )


@pytest.mark.parametrize("request_id", [
    "",
    "   ",
    "not-a-uuid",
    "00000000-0000-0000-0000-000000000000",
    123,
    True,
    uuid.uuid1(),
])
def test_invalid_request_id_changes_nothing(isolated_database, request_id):
    with isolated_database() as session:
        partner_id = add_partner(session)
        before = state(session, partner_id)

        with pytest.raises(ValueError, match="UUIDv4"):
            WithdrawalService(session).create_pending(
                partner_id,
                Decimal("10.00"),
                request_id=request_id,
            )
        session.commit()
        assert state(session, partner_id) == before


def test_invalid_amount_with_valid_key_is_still_rejected(isolated_database):
    with isolated_database() as session:
        partner_id = add_partner(session)
        before = state(session, partner_id)

        with pytest.raises(ValueError, match="two decimals"):
            WithdrawalService(session).create_pending(
                partner_id,
                Decimal("10.001"),
                request_id=str(uuid.uuid4()),
            )
        session.commit()
        assert state(session, partner_id) == before


def test_repeat_after_complete_returns_current_status(isolated_database):
    with isolated_database() as session:
        partner_id = add_partner(session)
        service = WithdrawalService(session)
        key = str(uuid.uuid4())
        withdrawal = service.create_pending(
            partner_id, Decimal("30.00"), request_id=key,
        )
        service.complete(withdrawal.id)
        session.commit()
        before = state(session, partner_id)

        again = service.create_pending(
            partner_id, Decimal("30.00"), request_id=key,
        )
        session.commit()

        assert again.id == withdrawal.id
        assert again.status == WithdrawalStatus.COMPLETED
        assert again.processed_at is not None
        assert state(session, partner_id) == before


def test_repeat_after_reject_returns_current_status(isolated_database):
    with isolated_database() as session:
        partner_id = add_partner(session)
        service = WithdrawalService(session)
        key = str(uuid.uuid4())
        withdrawal = service.create_pending(
            partner_id, Decimal("30.00"), request_id=key,
        )
        service.reject(withdrawal.id, admin_comment="Test rejection")
        session.commit()
        before = state(session, partner_id)

        again = service.create_pending(
            partner_id, Decimal("30.00"), request_id=key,
        )
        session.commit()

        assert again.id == withdrawal.id
        assert again.status == WithdrawalStatus.REJECTED
        assert again.admin_comment == "Test rejection"
        assert state(session, partner_id) == before


def test_insufficient_funds_with_key_leaves_no_withdrawal(isolated_database):
    with isolated_database() as session:
        partner_id = add_partner(session)
        before = state(session, partner_id)

        with pytest.raises(ValueError):
            WithdrawalService(session).create_pending(
                partner_id,
                Decimal("100.01"),
                request_id=str(uuid.uuid4()),
            )
        session.commit()
        assert state(session, partner_id) == before


def test_outer_rollback_removes_keyed_withdrawal(isolated_database):
    with isolated_database() as session:
        partner_id = add_partner(session)
        key = str(uuid.uuid4())
        before = state(session, partner_id)
        WithdrawalService(session).create_pending(
            partner_id,
            Decimal("30.00"),
            request_id=key,
        )
        session.rollback()

        assert state(session, partner_id) == before
        created = WithdrawalService(session).create_pending(
            partner_id,
            Decimal("30.00"),
            request_id=key,
        )
        session.commit()
        assert created.request_id == key
        assert state(session, partner_id)[3] == 1


def test_foreign_key_violation_is_not_treated_as_replay(isolated_database):
    with isolated_database() as session:
        with pytest.raises(IntegrityError):
            WithdrawalService(session).create_pending(
                partner_id=10**9,
                amount=Decimal("10.00"),
                request_id=str(uuid.uuid4()),
            )
        session.commit()
        assert session.query(Withdrawal).count() == 0
        assert session.query(Balance).count() == 0
        assert session.query(BalanceTransaction).count() == 0


def test_unrelated_integrity_error_is_not_a_replay(
    isolated_database, monkeypatch,
):
    with isolated_database() as session:
        partner_id = add_partner(session)
        service = WithdrawalService(session)
        before = state(session, partner_id)

        def fail_hold(*args, **kwargs):
            raise IntegrityError(
                "INSERT",
                {},
                Exception("CHECK constraint failed"),
            )

        monkeypatch.setattr(service.balance_service, "hold_funds", fail_hold)
        with pytest.raises(IntegrityError):
            service.create_pending(
                partner_id,
                Decimal("10.00"),
                request_id=str(uuid.uuid4()),
            )
        session.commit()
        assert state(session, partner_id) == before


def test_lost_insert_returns_existing_without_another_hold(isolated_database):
    with isolated_database() as session:
        partner_id = add_partner(session)
        service = WithdrawalService(session)
        key = str(uuid.uuid4())
        created = service.create_pending(
            partner_id, Decimal("15.00"), request_id=key,
        )
        session.commit()
        original = service._find_by_request_id
        calls = {"count": 0}

        def miss_first(partner, request_key):
            calls["count"] += 1
            if calls["count"] == 1:
                return None
            return original(partner, request_key)

        service._find_by_request_id = miss_first
        before = state(session, partner_id)
        again = service.create_pending(
            partner_id, Decimal("15.00"), request_id=key,
        )
        session.commit()

        assert calls["count"] >= 2
        assert again.id == created.id
        assert state(session, partner_id) == before


def test_lost_insert_with_different_data_conflicts_without_hold(
    isolated_database,
):
    with isolated_database() as session:
        partner_id = add_partner(session)
        service = WithdrawalService(session)
        key = str(uuid.uuid4())
        service.create_pending(
            partner_id,
            Decimal("15.00"),
            method="manual",
            request_id=key,
        )
        session.commit()
        original = service._find_by_request_id
        calls = {"count": 0}

        def miss_first(partner, request_key):
            calls["count"] += 1
            if calls["count"] == 1:
                return None
            return original(partner, request_key)

        service._find_by_request_id = miss_first
        before = state(session, partner_id)

        with pytest.raises(WithdrawalRequestConflict):
            service.create_pending(
                partner_id,
                Decimal("16.00"),
                method="manual",
                request_id=key,
            )
        session.commit()
        assert calls["count"] >= 2
        assert state(session, partner_id) == before


def _rows(connection, sql):
    return [tuple(row) for row in connection.execute(text(sql))]


def test_legacy_sqlite_migration_preserves_data_and_is_repeatable(tmp_path):
    database = tmp_path / "legacy-withdrawals.sqlite"
    assert database.name != "nanorem.db"
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    try:
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE partners ("
                "id INTEGER PRIMARY KEY, "
                "referral_code VARCHAR(32), "
                "upline_id INTEGER, "
                "root_id INTEGER, "
                "placement_version INTEGER NOT NULL DEFAULT 0, "
                "consent_given BOOLEAN NOT NULL DEFAULT 0, "
                "consent_version VARCHAR(50), "
                "consent_date DATETIME, "
                "annual_activity_until DATETIME)"
            ))
            connection.execute(text(
                "INSERT INTO partners "
                "(id, referral_code, root_id, placement_version, "
                "consent_given) "
                "VALUES (4, 'nr_legacy_partner_key', 4, 0, 0)"
            ))
            connection.execute(text(
                "CREATE TABLE balances ("
                "partner_id INTEGER PRIMARY KEY, "
                "amount NUMERIC NOT NULL, "
                "hold NUMERIC NOT NULL)"
            ))
            connection.execute(text(
                "INSERT INTO balances (partner_id, amount, hold) "
                "VALUES (4, '87.66', '12.34')"
            ))
            connection.execute(text(
                "CREATE TABLE withdrawals ("
                "id INTEGER PRIMARY KEY, "
                "partner_id INTEGER NOT NULL, "
                "amount NUMERIC NOT NULL, "
                "method VARCHAR NOT NULL, "
                "details JSON NOT NULL, "
                "status VARCHAR, "
                "created_at DATETIME, "
                "processed_at DATETIME, "
                "admin_comment TEXT)"
            ))
            connection.execute(text(
                "INSERT INTO withdrawals "
                "(id, partner_id, amount, method, details, status, "
                "created_at, processed_at, admin_comment) VALUES "
                "(1, 4, '12.34', 'manual', '{\"note\":\"legacy\"}', "
                "'pending', '2026-01-01 00:00:00', NULL, NULL), "
                "(2, 4, '8.00', 'manual', '{}', 'completed', "
                "'2026-01-02 00:00:00', '2026-01-03 00:00:00', 'done')"
            ))
            connection.execute(text(
                "CREATE TABLE balance_transactions ("
                "id INTEGER PRIMARY KEY, "
                "partner_id INTEGER NOT NULL, "
                "amount NUMERIC NOT NULL, "
                "type VARCHAR(30) NOT NULL, "
                "reference_id INTEGER, "
                "description VARCHAR)"
            ))
            connection.execute(text(
                "INSERT INTO balance_transactions "
                "(id, partner_id, amount, type, reference_id, description) "
                "VALUES (1, 4, '-12.34', 'WITHDRAWAL', 1, 'hold')"
            ))

        def snapshot():
            with engine.connect() as connection:
                return {
                    "partners": _rows(
                        connection,
                        "SELECT id, referral_code, root_id, "
                        "placement_version, consent_given "
                        "FROM partners ORDER BY id",
                    ),
                    "balances": _rows(
                        connection,
                        "SELECT partner_id, amount, hold "
                        "FROM balances ORDER BY partner_id",
                    ),
                    "withdrawals": _rows(
                        connection,
                        "SELECT id, partner_id, amount, method, details, "
                        "status, created_at, processed_at, admin_comment "
                        "FROM withdrawals ORDER BY id",
                    ),
                    "transactions": _rows(
                        connection,
                        "SELECT id, partner_id, amount, type, "
                        "reference_id, description "
                        "FROM balance_transactions ORDER BY id",
                    ),
                }

        before = snapshot()
        upgrade_schema(engine)
        upgrade_schema(engine)
        assert snapshot() == before

        inspector = inspect(engine)
        request_column = next(
            column for column in inspector.get_columns("withdrawals")
            if column["name"] == "request_id"
        )
        assert request_column["nullable"] is True
        with engine.connect() as connection:
            assert _rows(
                connection,
                "SELECT request_id FROM withdrawals ORDER BY id",
            ) == [(None,), (None,)]
            index_sql = connection.execute(text(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'index' "
                "AND name = 'uq_withdrawals_partner_request_id'"
            )).scalar_one()
        assert "UNIQUE" in index_sql.upper()
        assert "request_id IS NOT NULL" in index_sql

        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO withdrawals "
                "(partner_id, amount, method, details, request_id) "
                "VALUES (4, '1.00', 'manual', '{}', NULL)"
            ))
            connection.execute(text(
                "INSERT INTO withdrawals "
                "(partner_id, amount, method, details, request_id) "
                "VALUES (4, '1.00', 'manual', '{}', NULL)"
            ))
        with engine.connect() as connection:
            assert connection.execute(text(
                "SELECT COUNT(*) FROM withdrawals WHERE request_id IS NULL"
            )).scalar_one() == 4

        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO withdrawals "
                "(partner_id, amount, method, details, request_id) "
                "VALUES (4, '1.00', 'manual', '{}', :request_id)"
            ), {"request_id": "11111111-1111-4111-8111-111111111111"})
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(text(
                        "INSERT INTO withdrawals "
                        "(partner_id, amount, method, details, request_id) "
                        "VALUES (4, '2.00', 'bank', '{}', :request_id)"
                    ), {
                        "request_id": "11111111-1111-4111-8111-111111111111",
                    })
        with engine.connect() as connection:
            assert connection.execute(text(
                "SELECT COUNT(*) FROM withdrawals WHERE request_id = "
                "'11111111-1111-4111-8111-111111111111'"
            )).scalar_one() == 1
            balance_row = connection.execute(text(
                "SELECT amount, hold FROM balances WHERE partner_id = 4"
            )).one()
            assert tuple(Decimal(str(value)) for value in balance_row) == (
                Decimal("87.66"),
                Decimal("12.34"),
            )
    finally:
        engine.dispose()
