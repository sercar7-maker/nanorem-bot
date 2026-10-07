"""Read-only pre-deployment checks for an existing NANOREM database."""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Float,
    MetaData,
    Table,
    and_,
    create_engine,
    func,
    inspect,
    select,
    text,
)
from sqlalchemy.engine import Connection, Engine, make_url

logger = logging.getLogger(__name__)
_MAX_EXAMPLES = 100

# Kept local so importing this command cannot initialize application config,
# load .env, or construct the application database engine.
_UNIQUE_INDEXES = (
    ("partners", "uq_partners_telegram_id", ("telegram_id",), None),
    (
        "partners",
        "uq_partners_telegram_link_code",
        ("telegram_link_code",),
        None,
    ),
    (
        "purchases",
        "uq_purchases_ext_ref",
        ("ext_ref",),
        "ext_ref IS NOT NULL",
    ),
    (
        "purchases",
        "uq_purchases_purchase_number",
        ("purchase_number",),
        None,
    ),
    (
        "commissions",
        "uq_commissions_purchase_level",
        ("purchase_id", "level"),
        None,
    ),
    (
        "consent_versions",
        "uq_consent_versions_version",
        ("version",),
        None,
    ),
    ("users", "uq_users_email", ("email",), None),
    ("users", "uq_users_phone", ("phone",), None),
    (
        "balance_transactions",
        "uq_balance_tx_commission_reference",
        ("partner_id", "reference_id"),
        "type = 'COMMISSION' AND reference_id IS NOT NULL",
    ),
)
_MONEY_COLUMNS = {
    "balances": {"amount", "hold"},
    "balance_transactions": {"amount"},
    "purchases": {"amount"},
    "commissions": {"rate", "base_amount", "amount"},
    "withdrawals": {"amount"},
    "partner_stats": {
        "personal_turnover",
        "network_turnover",
        "monthly_personal_turnover",
        "monthly_network_turnover",
    },
}
_EXPECTED_FOREIGN_KEYS = (
    ("partners", ("upline_id",), "partners", ("id",)),
    ("purchases", ("partner_id",), "partners", ("id",)),
    ("commissions", ("partner_id",), "partners", ("id",)),
    ("commissions", ("purchase_id",), "purchases", ("id",)),
    ("commissions", ("source_partner_id",), "partners", ("id",)),
    ("balances", ("partner_id",), "partners", ("id",)),
    (
        "balance_transactions",
        ("partner_id",),
        "balances",
        ("partner_id",),
    ),
    ("withdrawals", ("partner_id",), "partners", ("id",)),
    ("partner_stats", ("partner_id",), "partners", ("id",)),
)


@dataclass
class Finding:
    severity: str
    code: str
    message: str
    examples: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0


@dataclass
class CheckReport:
    dialect: str
    root_count: int | None = None
    root_ids: list[int] = field(default_factory=list)
    sqlite_float_columns: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return not any(
            finding.severity in {"CRITICAL", "HIGH", "WARNING"}
            for finding in self.findings
        )


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _table(connection: Connection, name: str) -> Table | None:
    if not inspect(connection).has_table(name):
        return None
    return Table(name, MetaData(), autoload_with=connection)


def _primary_key_columns(table: Table) -> list:
    return list(table.primary_key.columns)


def _row_example(row: Any, columns: list) -> dict[str, Any]:
    return {
        column.name: _json_value(row._mapping[column.name])
        for column in columns
    }


def _required_unique_key_exists(
    connection: Connection,
    table_name: str,
    index_name: str,
    columns: tuple[str, ...],
    predicate: str | None,
) -> bool:
    if predicate == "lower_email":
        if connection.dialect.name == "sqlite":
            index_sql = connection.execute(
                text(
                    "SELECT sql FROM sqlite_master "
                    "WHERE type = 'index' AND name = :index_name"
                ),
                {"index_name": index_name},
            ).scalar_one_or_none()
        else:
            index_sql = connection.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE schemaname = current_schema() "
                    "AND tablename = :table_name "
                    "AND indexname = :index_name"
                ),
                {
                    "table_name": table_name,
                    "index_name": index_name,
                },
            ).scalar_one_or_none()
        normalized_sql = re.sub(
            r'[\s"\[\]`]', "", (index_sql or "")
        ).lower()
        return (
            "createuniqueindex" in normalized_sql
            and "lower(" in normalized_sql
            and bool(
                re.search(
                    r"lower\(\(*(?:partners\.)?email",
                    normalized_sql,
                )
            )
        )
    inspector = inspect(connection)
    if any(
        tuple(constraint.get("column_names") or ()) == columns
        for constraint in inspector.get_unique_constraints(table_name)
    ):
        return True
    for index in inspector.get_indexes(table_name):
        if not index.get("unique"):
            continue
        if tuple(index.get("column_names") or ()) != columns:
            continue
        actual_predicate = (
            index.get("dialect_options", {}).get(
                f"{connection.dialect.name}_where"
            )
        )
        if actual_predicate is None:
            return True
        if (
            predicate is not None
            and _normalize_predicate(actual_predicate)
            == _normalize_predicate(predicate)
        ):
            return True
    return False


def _normalize_predicate(value: Any) -> str:
    return re.sub(r'[\s()"\[\]`]', "", str(value)).lower()


def _add_duplicate_findings(
    connection: Connection,
    report: CheckReport,
) -> None:
    duplicate_keys = [
        (table_name, index_name, columns, predicate)
        for table_name, index_name, columns, predicate in _UNIQUE_INDEXES
    ]
    duplicate_keys.append(
        (
            "partners",
            "uq_partners_email_normalized",
            ("email",),
            "lower_email",
        )
    )

    for table_name, index_name, column_names, predicate in duplicate_keys:
        table = _table(connection, table_name)
        if table is None or not set(column_names).issubset(table.c.keys()):
            continue
        if _required_unique_key_exists(
            connection,
            table_name,
            index_name,
            column_names,
            predicate,
        ):
            continue

        key_columns = [
            func.lower(table.c.email).label("normalized_email")
            if predicate == "lower_email"
            else table.c[name]
            for name in column_names
        ]
        conditions = []
        if predicate == "ext_ref IS NOT NULL":
            conditions.append(table.c.ext_ref.is_not(None))
        elif predicate == (
            "type = 'COMMISSION' AND reference_id IS NOT NULL"
        ):
            conditions.extend(
                [
                    table.c.type == "COMMISSION",
                    table.c.reference_id.is_not(None),
                ]
            )
        elif predicate == "lower_email":
            conditions.append(table.c.email.is_not(None))

        duplicate_query = (
            select(*key_columns, func.count().label("duplicate_count"))
            .select_from(table)
            .group_by(*key_columns)
            .having(func.count() > 1)
        )
        if conditions:
            duplicate_query = duplicate_query.where(and_(*conditions))

        total_groups = connection.execute(
            select(func.count()).select_from(duplicate_query.subquery())
        ).scalar_one()
        duplicate_rows = (
            connection.execute(
                duplicate_query.limit(_MAX_EXAMPLES)
            )
            .mappings()
            .all()
        )
        if not duplicate_rows:
            continue

        primary_keys = _primary_key_columns(table)
        examples: list[dict[str, Any]] = []
        for duplicate in duplicate_rows[:_MAX_EXAMPLES]:
            key_values = list(duplicate.values())[:-1]
            row_conditions = []
            for column, value in zip(key_columns, key_values):
                if column.name == "normalized_email":
                    row_conditions.append(
                        func.lower(table.c.email) == value
                    )
                else:
                    row_conditions.append(
                        table.c[column.name].is_(None)
                        if value is None
                        else table.c[column.name] == value
                    )
            if predicate == "ext_ref IS NOT NULL":
                row_conditions.append(table.c.ext_ref.is_not(None))
            elif predicate == (
                "type = 'COMMISSION' AND reference_id IS NOT NULL"
            ):
                row_conditions.extend(
                    [
                        table.c.type == "COMMISSION",
                        table.c.reference_id.is_not(None),
                    ]
                )
            matching_rows = connection.execute(
                select(
                    *primary_keys,
                    *(table.c[name] for name in column_names),
                )
                .where(and_(*row_conditions))
                .limit(_MAX_EXAMPLES)
            ).all()
            displayed_rows = [
                _row_example(
                    row,
                    [
                        *primary_keys,
                        *(table.c[name] for name in column_names),
                    ],
                )
                for row in matching_rows
            ]
            examples.append(
                {
                    "key": {
                        column.name: _json_value(value)
                        for column, value in zip(key_columns, key_values)
                    },
                    "count": duplicate["duplicate_count"],
                    "rows": displayed_rows,
                    "rows_omitted": max(
                        0,
                        duplicate["duplicate_count"] - len(displayed_rows),
                    ),
                }
            )

        report.findings.append(
            Finding(
                severity="HIGH",
                code="DUPLICATE_UNIQUE_KEY",
                message=(
                    f"{table_name}.{index_name}: duplicate key groups "
                    "match the current migration duplicate scan. Groups "
                    "with NULL values may be accepted by the database's "
                    "unique index but can still stop that migration."
                ),
                examples=examples,
                total=total_groups,
            )
        )


def _add_orphan_findings(
    connection: Connection,
    report: CheckReport,
) -> None:
    inspector = inspect(connection)
    actual_tables = set(inspector.get_table_names())
    expected_fks: set[tuple[str, tuple[str, ...], str, tuple[str, ...]]] = set()
    actual_fks: set[tuple[str, tuple[str, ...], str, tuple[str, ...]]] = set()

    expected_fks.update(_EXPECTED_FOREIGN_KEYS)

    for table_name in actual_tables:
        for foreign_key in inspector.get_foreign_keys(table_name):
            target_table = foreign_key.get("referred_table")
            local_columns = tuple(foreign_key.get("constrained_columns") or ())
            remote_columns = tuple(foreign_key.get("referred_columns") or ())
            if target_table and local_columns and remote_columns:
                actual_fks.add(
                    (table_name, local_columns, target_table, remote_columns)
                )

    missing_fks = expected_fks - actual_fks
    for table_name, local_columns, target_table, remote_columns in sorted(
        missing_fks
    ):
        if table_name not in actual_tables:
            continue
        report.findings.append(
            Finding(
                severity="WARNING",
                code="MISSING_FOREIGN_KEY",
                message=(
                    f"Schema does not declare FK "
                    f"{table_name}{local_columns} -> "
                    f"{target_table}{remote_columns}"
                ),
            )
        )

    for table_name, local_columns, target_table, remote_columns in sorted(
        actual_fks | (expected_fks & {
            fk for fk in expected_fks
            if fk[0] in actual_tables and fk[2] in actual_tables
        })
    ):
        if table_name not in actual_tables or target_table not in actual_tables:
            continue
        child = _table(connection, table_name)
        parent_table = _table(connection, target_table)
        if (
            child is None
            or parent_table is None
            or not set(local_columns).issubset(child.c.keys())
            or not set(remote_columns).issubset(parent_table.c.keys())
        ):
            continue
        parent = parent_table.alias("fk_parent")

        join_condition = and_(
            *(
                child.c[local] == parent.c[remote]
                for local, remote in zip(local_columns, remote_columns)
            )
        )
        child_keys_present = and_(
            *(child.c[column].is_not(None) for column in local_columns)
        )
        primary_keys = _primary_key_columns(child)
        selected_columns = list(dict.fromkeys(
            [*primary_keys, *(child.c[name] for name in local_columns)]
        ))
        query = (
            select(*selected_columns)
            .select_from(child.outerjoin(parent, join_condition))
            .where(
                child_keys_present,
                parent.c[remote_columns[0]].is_(None),
            )
        )
        result = connection.execute(query)
        examples = []
        count = 0
        for row in result:
            count += 1
            if len(examples) < _MAX_EXAMPLES:
                examples.append(_row_example(row, selected_columns))
        if count:
            report.findings.append(
                Finding(
                    severity="HIGH",
                    code="ORPHAN_FOREIGN_KEY",
                    message=(
                        f"{table_name}{local_columns} contains references "
                        f"missing from {target_table}{remote_columns}"
                    ),
                    examples=examples,
                    total=count,
                )
            )


def _add_financial_findings(
    connection: Connection,
    report: CheckReport,
) -> None:
    checks = {
        "balances": {
            "amount": ("<", 0),
            "hold": ("<", 0),
        },
        "purchases": {
            "amount": ("<=", 0),
        },
        "commissions": {
            "rate": ("<=", 0),
            "base_amount": ("<=", 0),
            "amount": ("<=", 0),
        },
        "withdrawals": {
            "amount": ("<=", 0),
        },
        "partner_stats": {
            "personal_turnover": ("<", 0),
            "network_turnover": ("<", 0),
            "monthly_personal_turnover": ("<", 0),
            "monthly_network_turnover": ("<", 0),
        },
        "balance_transactions": {
            "amount": ("<=", 0),
        },
    }
    for table_name, columns in checks.items():
        table = _table(connection, table_name)
        if table is None:
            continue
        for column_name, (operator, threshold) in columns.items():
            if column_name not in table.c:
                continue
            condition = (
                table.c[column_name] < threshold
                if operator == "<"
                else table.c[column_name] <= threshold
            )
            if table_name == "balance_transactions":
                if "type" not in table.c:
                    continue
                condition = and_(
                    condition,
                    table.c.type == "COMMISSION",
                )
            primary_keys = _primary_key_columns(table)
            selected = [*primary_keys, table.c[column_name]]
            rows = connection.execute(
                select(*selected).where(condition)
            )
            examples = [
                _row_example(row, selected)
                for row in rows.fetchmany(_MAX_EXAMPLES)
            ]
            total = connection.execute(
                select(func.count())
                .select_from(table)
                .where(condition)
            ).scalar_one()
            if total:
                report.findings.append(
                    Finding(
                        severity="HIGH",
                        code="INVALID_FINANCIAL_VALUE",
                        message=(
                            f"{table_name}.{column_name} has "
                            f"{operator} {threshold} values"
                        ),
                        examples=examples,
                        total=total,
                    )
                )


def _add_root_report(
    connection: Connection,
    report: CheckReport,
) -> None:
    partners = _table(connection, "partners")
    if partners is None or not {"id", "upline_id"}.issubset(partners.c.keys()):
        report.findings.append(
            Finding(
                severity="WARNING",
                code="ROOT_SCHEMA_UNAVAILABLE",
                message="Cannot inspect roots: partners.id/upline_id is absent",
            )
        )
        return

    rows = connection.execute(
        select(partners.c.id)
        .where(partners.c.upline_id.is_(None))
        .order_by(partners.c.id)
    ).scalars().all()
    report.root_count = len(rows)
    report.root_ids = list(rows)
    if report.root_count > 2:
        report.findings.append(
            Finding(
                severity="CRITICAL",
                code="TOO_MANY_ROOTS",
                message=(
                    f"Found {report.root_count} roots; business rule allows "
                    "at most two"
                ),
                examples=[{"root_id": root_id} for root_id in rows],
                total=report.root_count,
            )
        )
    elif report.root_count < 2:
        report.findings.append(
            Finding(
                severity="WARNING",
                code="FEWER_THAN_TWO_ROOTS",
                message=(
                    f"Found {report.root_count} roots; no root was created "
                    "or changed by this check"
                ),
                examples=[{"root_id": root_id} for root_id in rows],
                total=report.root_count,
            )
        )


def _find_sqlite_float_columns(
    connection: Connection,
    report: CheckReport,
) -> None:
    if connection.dialect.name != "sqlite":
        return

    inspector = inspect(connection)
    for table_name, expected_columns in _MONEY_COLUMNS.items():
        if not inspector.has_table(table_name):
            continue
        for column in inspector.get_columns(table_name):
            if (
                column["name"] in expected_columns
                and isinstance(column["type"], Float)
            ):
                report.sqlite_float_columns.append(
                    f"{table_name}.{column['name']} ({column['type']})"
                )
    if report.sqlite_float_columns:
        report.findings.append(
            Finding(
                severity="WARNING",
                code="SQLITE_LEGACY_FLOAT",
                message=(
                    "SQLite monetary/turnover columns still use FLOAT; "
                    "no conversion was attempted"
                ),
                examples=[
                    {"column": column}
                    for column in report.sqlite_float_columns
                ],
                total=len(report.sqlite_float_columns),
            )
        )


def inspect_database(connection: Connection) -> CheckReport:
    """Collect read-only diagnostics using the supplied open connection."""
    report = CheckReport(dialect=connection.dialect.name)
    _add_root_report(connection, report)
    _add_duplicate_findings(connection, report)
    _add_orphan_findings(connection, report)
    _add_financial_findings(connection, report)
    _find_sqlite_float_columns(connection, report)
    return report


def check_database(engine: Engine) -> CheckReport:
    """Run checks in a database-enforced read-only transaction."""
    if engine.dialect.name not in {"sqlite", "postgresql"}:
        raise RuntimeError(
            "Pre-deploy diagnostics support SQLite and PostgreSQL only"
        )
    with engine.connect() as connection:
        with connection.begin():
            if connection.dialect.name == "sqlite":
                connection.exec_driver_sql("PRAGMA query_only = ON")
            else:
                connection.exec_driver_sql(
                    "SET TRANSACTION READ ONLY"
                )
            return inspect_database(connection)


def _read_only_database_url(database_url: str) -> str:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        return database_url
    database = url.database
    if not database or database == ":memory:":
        return database_url
    query = dict(url.query)
    if database.startswith("file:"):
        if query.get("mode") != "ro":
            raise ValueError(
                "SQLite file: URLs must specify mode=ro for a read-only check"
            )
        query["uri"] = "true"
        return str(url.set(query=query))

    path = Path(database).expanduser()
    if not path.is_file():
        raise FileNotFoundError(
            "SQLite database file does not exist; refusing to create a new "
            "database during a pre-deploy check"
        )
    query.update({"mode": "ro", "uri": "true"})
    return str(
        url.set(
            database=f"file:{path.resolve().as_posix()}",
            query=query,
        )
    )


def _format_report(report: CheckReport) -> str:
    lines = [
        f"Read-only pre-deploy check ({report.dialect})",
        f"Roots: {report.root_count}; IDs: {report.root_ids}",
    ]
    if report.sqlite_float_columns:
        lines.append(
            "Legacy SQLite FLOAT columns: "
            + ", ".join(report.sqlite_float_columns)
        )
    for finding in report.findings:
        lines.append(
            f"{finding.severity} [{finding.code}] {finding.message} "
            f"(groups/rows: {finding.total})"
        )
        for example in finding.examples:
            lines.append(
                "  " + json.dumps(
                    example,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
            )
        if finding.total > len(finding.examples):
            lines.append(
                f"  ... {finding.total - len(finding.examples)} more "
                "not displayed"
            )

    if report.ready:
        lines.append("RESULT: READY — no blocking or review findings")
        return "\n".join(lines)
    blocking = any(
        finding.severity in {"CRITICAL", "HIGH"}
        for finding in report.findings
    )
    lines.append(
        "RESULT: BLOCKED — resolve reported findings before migration"
        if blocking
        else "RESULT: REVIEW — inspect warnings before migration"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only schema/data pre-deployment check. Does not load .env, "
            "run migrations, or repair data."
        )
    )
    parser.add_argument(
        "--database-url",
        required=True,
        help=(
            "Explicit SQLAlchemy URL for the database to inspect; it is not "
            "read from application config or .env"
        ),
    )
    args = parser.parse_args(argv)

    engine = None
    try:
        read_only_url = _read_only_database_url(args.database_url)
        engine = create_engine(read_only_url)
        report = check_database(engine)
        print(_format_report(report))
        return 0 if report.ready else 1
    except Exception as exc:
        logger.error("Read-only pre-deploy check failed: %s", exc)
        print(
            f"CHECK FAILED: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
