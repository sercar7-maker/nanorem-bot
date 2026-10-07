from decimal import Decimal
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from database.base import Base
from database.models import (
    Commission,
    CommissionStatus,
    OrderStatus,
    Partner,
    Purchase,
    Withdrawal,
    WithdrawalStatus,
)
from database.models_balance import (
    Balance,
    BalanceTransaction,
    BalanceTransactionType,
)
from database.models_stats import PartnerStats
from pre_deploy_check import check_database, _read_only_database_url


@pytest.fixture
def diagnostic_engine():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


def _finding(report, code):
    return [finding for finding in report.findings if finding.code == code]


def test_clean_database_reports_two_roots_and_no_findings(
    diagnostic_engine,
):
    with diagnostic_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO partners "
                "(id, telegram_id, telegram_link_code, referral_code, "
                "upline_id, consent_given) "
                "VALUES (10, 'tg10', 'code10', 'nr_test_root_10', NULL, 0), "
                "(20, 'tg20', 'code20', 'nr_test_root_20', NULL, 0)"
            )
        )

    report = check_database(diagnostic_engine)

    assert report.root_count == 2
    assert report.root_ids == [10, 20]
    assert report.findings == []
    with diagnostic_engine.connect() as connection:
        assert connection.exec_driver_sql(
            "PRAGMA query_only"
        ).scalar_one() == 1
        assert connection.execute(
            text("SELECT COUNT(*) FROM partners")
        ).scalar_one() == 2
        with pytest.raises(DBAPIError):
            connection.execute(
                text("INSERT INTO partners (id) VALUES (30)")
            )


def test_email_duplicates_are_reported_case_insensitively_and_null_ignored(
    diagnostic_engine,
):
    index = next(
        index
        for index in Partner.__table__.indexes
        if index.name == "uq_partners_email_normalized"
    )
    index.drop(diagnostic_engine)
    with diagnostic_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO partners "
                "(id, telegram_id, telegram_link_code, referral_code, email, upline_id, "
                "consent_given) VALUES "
                "(1, 'tg1', 'code1', 'nr_test_email_1', "
                "'Buyer@Example.Test', NULL, 0), "
                "(2, 'tg2', 'code2', 'nr_test_email_2', "
                "'buyer@example.test', NULL, 0), "
                "(3, 'tg3', 'code3', 'nr_test_email_3', NULL, NULL, 0), "
                "(4, 'tg4', 'code4', 'nr_test_email_4', NULL, NULL, 0)"
            )
        )

    report = check_database(diagnostic_engine)
    duplicate_findings = [
        finding
        for finding in _finding(report, "DUPLICATE_UNIQUE_KEY")
        if "uq_partners_email_normalized" in finding.message
    ]

    assert len(duplicate_findings) == 1
    assert duplicate_findings[0].total == 1
    example = duplicate_findings[0].examples[0]
    assert example["key"] == {"normalized_email": "buyer@example.test"}
    assert {row["id"] for row in example["rows"]} == {1, 2}


def test_orphan_foreign_keys_are_reported_read_only(diagnostic_engine):
    with diagnostic_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO purchases "
                "(id, purchase_number, partner_id, amount) "
                "VALUES (501, 'orphan-purchase', 99001, 10)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO commissions "
                "(id, partner_id, purchase_id, source_partner_id, "
                "level, rate, base_amount, amount) "
                "VALUES (601, 99002, 99003, 99004, 1, 0.2, 10, 2)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO balances (partner_id, amount, hold) "
                "VALUES (99005, 0, 0)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO balance_transactions "
                "(id, partner_id, amount, type) "
                "VALUES (701, 99006, 10, 'COMMISSION')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO partner_stats "
                "(partner_id, personal_turnover, network_turnover, "
                "monthly_personal_turnover, monthly_network_turnover) "
                "VALUES (99007, 0, 0, 0, 0)"
            )
        )

    report = check_database(diagnostic_engine)
    orphan_findings = _finding(report, "ORPHAN_FOREIGN_KEY")
    messages = [finding.message for finding in orphan_findings]

    assert len(orphan_findings) >= 7
    assert any("purchases" in message for message in messages)
    assert any("commissions" in message for message in messages)
    assert any("balances" in message for message in messages)
    assert any("balance_transactions" in message for message in messages)
    assert any("partner_stats" in message for message in messages)
    assert all(finding.total >= 1 for finding in orphan_findings)
    with diagnostic_engine.connect() as connection:
        assert connection.execute(
            text("SELECT COUNT(*) FROM purchases WHERE id = 501")
        ).scalar_one() == 1


def test_more_than_two_roots_is_critical_and_fewer_than_two_is_reported(
    diagnostic_engine,
):
    with diagnostic_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO partners "
                "(id, telegram_id, telegram_link_code, referral_code, "
                "upline_id, consent_given) "
                "VALUES (11, 'tg11', 'code11', 'nr_test_root_11', NULL, 0), "
                "(12, 'tg12', 'code12', 'nr_test_root_12', NULL, 0), "
                "(13, 'tg13', 'code13', 'nr_test_root_13', NULL, 0)"
            )
        )

    report = check_database(diagnostic_engine)

    assert report.root_count == 3
    assert report.root_ids == [11, 12, 13]
    assert _finding(report, "TOO_MANY_ROOTS")[0].severity == "CRITICAL"

    one_root_engine = create_engine("sqlite://")
    try:
        Base.metadata.create_all(one_root_engine)
        with one_root_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO partners "
                    "(id, telegram_id, telegram_link_code, referral_code, "
                    "upline_id, consent_given) VALUES "
                    "(31, 'tg31', 'code31', 'nr_test_root_31', NULL, 0)"
                )
            )
        one_root_report = check_database(one_root_engine)
        assert one_root_report.root_count == 1
        assert _finding(one_root_report, "FEWER_THAN_TWO_ROOTS")
    finally:
        one_root_engine.dispose()


def test_negative_and_nonpositive_financial_values_are_reported(
    diagnostic_engine,
):
    with diagnostic_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO partners "
                "(id, telegram_id, telegram_link_code, referral_code, "
                "upline_id, consent_given) VALUES "
                "(1, 'tg1', 'code1', 'nr_test_root_financial', NULL, 0)"
            )
        )
    session = Session(diagnostic_engine)
    try:
        session.add_all(
            [
                Balance(partner_id=1, amount=Decimal("-1"), hold=Decimal("-2")),
                Purchase(
                    purchase_number="negative-purchase",
                    partner_id=1,
                    amount=Decimal("-1"),
                    status=OrderStatus.PAID,
                ),
                Commission(
                    partner_id=1,
                    purchase_id=1,
                    level=1,
                    rate=Decimal("-0.2"),
                    base_amount=Decimal("-10"),
                    amount=Decimal("-2"),
                ),
                Withdrawal(
                    partner_id=1,
                    amount=Decimal("0"),
                    method="manual",
                    details={},
                    status=WithdrawalStatus.PENDING,
                ),
                PartnerStats(
                    partner_id=1,
                    personal_turnover=Decimal("-1"),
                    network_turnover=Decimal("-1"),
                    monthly_personal_turnover=Decimal("-1"),
                    monthly_network_turnover=Decimal("-1"),
                ),
                BalanceTransaction(
                    partner_id=1,
                    amount=Decimal("0"),
                    type=BalanceTransactionType.COMMISSION,
                    reference_id=901,
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    report = check_database(diagnostic_engine)
    invalid = _finding(report, "INVALID_FINANCIAL_VALUE")

    assert len(invalid) >= 10
    assert any("balances.amount" in finding.message for finding in invalid)
    assert any("balances.hold" in finding.message for finding in invalid)
    assert any("purchases.amount" in finding.message for finding in invalid)
    assert any("withdrawals.amount" in finding.message for finding in invalid)
    assert any("partner_stats" in finding.message for finding in invalid)


def test_duplicate_idempotency_keys_are_reported(diagnostic_engine):
    with diagnostic_engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE balance_transactions")
        connection.exec_driver_sql("DROP TABLE commissions")
        connection.exec_driver_sql("DROP TABLE purchases")
        connection.exec_driver_sql("DROP TABLE balances")
        connection.exec_driver_sql(
            "CREATE TABLE purchases "
            "(id INTEGER PRIMARY KEY, ext_ref TEXT, purchase_number TEXT)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE commissions "
            "(id INTEGER PRIMARY KEY, partner_id INTEGER, purchase_id INTEGER, "
            "level INTEGER)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE balances "
            "(partner_id INTEGER PRIMARY KEY)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE balance_transactions "
            "(id INTEGER PRIMARY KEY, partner_id INTEGER, amount NUMERIC, "
            "reference_id INTEGER, type TEXT)"
        )
        connection.execute(
            text(
                "INSERT INTO purchases "
                "(id, purchase_number, ext_ref) "
                "VALUES "
                "(101, 'legacy-1', 'order-dup'), "
                "(102, 'legacy-2', 'order-dup')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO commissions "
                "(id, partner_id, purchase_id, level) VALUES "
                "(201, 1, 101, 1), "
                "(202, 1, 101, 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO balances (partner_id) VALUES (1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO balance_transactions "
                "(id, partner_id, amount, type, reference_id) VALUES "
                "(301, 1, 2, 'COMMISSION', 201), "
                "(302, 1, 2, 'COMMISSION', 201)"
            )
        )

    report = check_database(diagnostic_engine)
    findings = _finding(report, "DUPLICATE_UNIQUE_KEY")
    messages = [finding.message for finding in findings]

    assert any("uq_purchases_ext_ref" in message for message in messages)
    assert any("uq_commissions_purchase_level" in message for message in messages)
    assert any(
        "uq_balance_tx_commission_reference" in message
        for message in messages
    )


def test_sqlite_float_money_columns_are_listed_without_conversion():
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE purchases "
                    "(id INTEGER PRIMARY KEY, amount FLOAT)"
                )
            )
            connection.execute(
                text(
                    "CREATE TABLE balances "
                    "(partner_id INTEGER PRIMARY KEY, amount FLOAT, hold FLOAT)"
                )
            )

        report = check_database(engine)

        assert set(report.sqlite_float_columns) == {
            "purchases.amount (FLOAT)",
            "balances.amount (FLOAT)",
            "balances.hold (FLOAT)",
        }
        with engine.connect() as connection:
            columns = inspect(connection).get_columns("purchases")
            amount_column = next(
                column for column in columns if column["name"] == "amount"
            )
            assert str(amount_column["type"]).upper() == "FLOAT"
    finally:
        engine.dispose()


def test_missing_sqlite_database_path_is_not_created(tmp_path):
    from pre_deploy_check import main

    missing = tmp_path / "does-not-exist.db"
    result = main(["--database-url", f"sqlite:///{missing.as_posix()}"])

    assert result == 2
    assert not missing.exists()


def test_existing_sqlite_file_is_opened_in_read_only_uri_mode(tmp_path):
    database = tmp_path / "readonly-copy.db"
    initial_engine = create_engine(f"sqlite:///{database.as_posix()}")
    Base.metadata.create_all(initial_engine)
    initial_engine.dispose()

    read_only_url = _read_only_database_url(
        f"sqlite:///{database.as_posix()}"
    )
    assert "mode=ro" in read_only_url
    read_only_engine = create_engine(read_only_url)
    try:
        report = check_database(read_only_engine)
        assert report.dialect == "sqlite"
        with read_only_engine.connect() as connection:
            assert connection.exec_driver_sql(
                "PRAGMA query_only"
            ).scalar_one() == 1
    finally:
        read_only_engine.dispose()


def test_cli_help_does_not_load_application_config_or_dotenv():
    script = Path(__file__).resolve().parents[1] / "pre_deploy_check.py"
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=script.parent,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Read-only schema/data pre-deployment check" in result.stdout
    assert "Configuration Loaded:" not in result.stdout
    assert "BOT_TOKEN" not in result.stdout
