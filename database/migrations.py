import logging
import re

from sqlalchemy import Float, Engine, inspect, text


logger = logging.getLogger(__name__)

_UNIQUE_INDEXES = (
    (
        "partners",
        "uq_partners_telegram_id",
        ("telegram_id",),
        None,
    ),
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
    (
        "users",
        "uq_users_email",
        ("email",),
        None,
    ),
    (
        "users",
        "uq_users_phone",
        ("phone",),
        None,
    ),
    (
        "balance_transactions",
        "uq_balance_tx_commission_reference",
        ("partner_id", "reference_id"),
        "type = 'COMMISSION' AND reference_id IS NOT NULL",
    ),
)

_MONEY_COLUMNS = {
    "balances": {"amount": 2, "hold": 2},
    "balance_transactions": {"amount": 2},
    "purchases": {"amount": 2},
    "commissions": {"rate": 4, "base_amount": 2, "amount": 2},
    "withdrawals": {"amount": 2},
    "partner_stats": {
        "personal_turnover": 2,
        "network_turnover": 2,
        "monthly_personal_turnover": 2,
        "monthly_network_turnover": 2,
    },
}


def _add_consent_columns(connection, inspector) -> None:
    if not inspector.has_table("partners"):
        return

    present = {
        column["name"] for column in inspector.get_columns("partners")
    }
    boolean_default = "0" if connection.dialect.name == "sqlite" else "FALSE"
    definitions = {
        "consent_given": (
            f"BOOLEAN NOT NULL DEFAULT {boolean_default}"
        ),
        "consent_version": "VARCHAR(50)",
        "consent_date": (
            "DATETIME" if connection.dialect.name == "sqlite" else "TIMESTAMP"
        ),
    }

    for name, definition in definitions.items():
        if name not in present:
            connection.execute(
                text(
                    f"ALTER TABLE partners "
                    f"ADD COLUMN {name} {definition}"
                )
            )


def _normalize_predicate(predicate) -> str | None:
    if predicate is None:
        return None
    return re.sub(r'[\s()"\[\]`]', "", str(predicate)).lower()


def _index_predicate(index: dict, dialect_name: str) -> str | None:
    options = index.get("dialect_options") or {}
    return options.get(f"{dialect_name}_where")


def _index_matches(
    index: dict,
    columns: tuple[str, ...],
    predicate: str | None,
    dialect_name: str,
) -> bool:
    if not index.get("unique"):
        return False
    if tuple(index.get("column_names") or ()) != columns:
        return False

    actual_predicate = _normalize_predicate(
        _index_predicate(index, dialect_name)
    )
    expected_predicate = _normalize_predicate(predicate)

    # Unique indexes already treat NULL keys as distinct, so an explicit
    # IS NOT NULL clause on an indexed column does not change enforcement.
    for column in columns:
        null_guard = f"and{column.lower()}isnotnull"
        if actual_predicate:
            actual_predicate = actual_predicate.replace(null_guard, "")
        if expected_predicate:
            expected_predicate = expected_predicate.replace(null_guard, "")

    # A full unique index also enforces a nullable-key partial unique index.
    if actual_predicate is None:
        return True
    return actual_predicate == expected_predicate


def _has_unique_key(
    inspector,
    table: str,
    columns: tuple[str, ...],
    predicate: str | None,
    dialect_name: str,
):
    constraints = inspector.get_unique_constraints(table)
    if any(
        tuple(constraint.get("column_names") or ()) == columns
        for constraint in constraints
    ):
        return True

    indexes = inspector.get_indexes(table)
    return any(
        _index_matches(index, columns, predicate, dialect_name)
        for index in indexes
    )


def _create_unique_index(
    connection,
    inspector,
    table: str,
    index_name: str,
    columns: tuple[str, ...],
    predicate: str | None,
) -> None:
    if not inspector.has_table(table):
        return

    present_columns = {
        column["name"] for column in inspector.get_columns(table)
    }
    if not set(columns).issubset(present_columns):
        missing = ", ".join(sorted(set(columns) - present_columns))
        logger.warning(
            "Skipping %s because table %s is missing column(s): %s",
            index_name,
            table,
            missing,
        )
        return

    indexes = inspector.get_indexes(table)
    named_index = next(
        (index for index in indexes if index.get("name") == index_name),
        None,
    )
    if named_index and not _index_matches(
        named_index,
        columns,
        predicate,
        connection.dialect.name,
    ):
        raise RuntimeError(
            f"Cannot apply {index_name}: an index with that name exists "
            "but does not enforce the required unique key"
        )

    if _has_unique_key(
        inspector,
        table,
        columns,
        predicate,
        connection.dialect.name,
    ):
        return

    columns_sql = ", ".join(columns)
    where_sql = f" WHERE {predicate}" if predicate else ""
    duplicate_columns = ", ".join(columns)
    duplicate = connection.execute(
        text(
            f"SELECT {duplicate_columns}, COUNT(*) "
            f"FROM {table} "
            f"{f'WHERE {predicate} ' if predicate else ''}"
            f"GROUP BY {duplicate_columns} "
            f"HAVING COUNT(*) > 1 "
            f"LIMIT 1"
        )
    ).first()
    if duplicate:
        raise RuntimeError(
            f"Cannot create {index_name}: duplicate rows exist in {table} "
            f"for columns ({columns_sql}). Diagnose with: SELECT "
            f"{duplicate_columns}, COUNT(*) FROM {table} "
            f"{f'WHERE {predicate} ' if predicate else ''}"
            f"GROUP BY {duplicate_columns} HAVING COUNT(*) > 1"
        )

    connection.execute(
        text(
            f"CREATE UNIQUE INDEX {index_name} "
            f"ON {table} ({columns_sql}){where_sql}"
        )
    )
    inspector.clear_cache()


def _upgrade_postgresql_money_types(connection, inspector) -> None:
    if connection.dialect.name != "postgresql":
        return

    for table, columns in _MONEY_COLUMNS.items():
        if not inspector.has_table(table):
            continue

        types = {
            column["name"]: column["type"]
            for column in inspector.get_columns(table)
        }
        for column, scale in columns.items():
            if column not in types or not isinstance(types[column], Float):
                continue

            precision = 5 if column == "rate" else 18
            connection.execute(
                text(
                    f"ALTER TABLE {table} "
                    f"ALTER COLUMN {column} TYPE NUMERIC({precision}, {scale}) "
                    f"USING ROUND({column}::numeric, {scale})"
                )
            )
            inspector.clear_cache()


def upgrade_schema(engine: Engine) -> None:
    """Apply safe, additive upgrades for schemas created before these models."""
    with engine.begin() as connection:
        inspector = inspect(connection)
        _add_consent_columns(connection, inspector)

        for table, index_name, columns, predicate in _UNIQUE_INDEXES:
            _create_unique_index(
                connection,
                inspector,
                table,
                index_name,
                columns,
                predicate,
            )

        _upgrade_postgresql_money_types(connection, inspector)

        if connection.dialect.name == "sqlite":
            for table, columns in _MONEY_COLUMNS.items():
                if not inspector.has_table(table):
                    continue
                legacy_columns = [
                    column["name"]
                    for column in inspector.get_columns(table)
                    if column["name"] in columns
                    and isinstance(column["type"], Float)
                ]
                if legacy_columns:
                    logger.warning(
                        "SQLite table %s has legacy floating-point monetary "
                        "column(s) %s; schema was not altered. Back up the "
                        "database and use a reviewed offline table rebuild.",
                        table,
                        ", ".join(legacy_columns),
                    )
