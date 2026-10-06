import logging

from sqlalchemy import Float, Engine, inspect, text


logger = logging.getLogger(__name__)

_UNIQUE_INDEXES = (
    (
        "purchases",
        "uq_purchases_ext_ref",
        ("ext_ref",),
        "ext_ref IS NOT NULL",
    ),
    (
        "commissions",
        "uq_commissions_purchase_level",
        ("purchase_id", "level"),
        None,
    ),
)

_MONEY_COLUMNS = {
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


def _has_unique_key(inspector, table: str, name: str, columns: tuple[str, ...]):
    constraints = inspector.get_unique_constraints(table)
    if any(
        constraint.get("name") == name
        or tuple(constraint.get("column_names") or ()) == columns
        for constraint in constraints
    ):
        return True

    indexes = inspector.get_indexes(table)
    return any(
        index.get("unique")
        and (
            index.get("name") == name
            or tuple(index.get("column_names") or ()) == columns
        )
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
    if not inspector.has_table(table) or _has_unique_key(
        inspector,
        table,
        index_name,
        columns,
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
            f"Cannot create {index_name}: duplicate rows exist in {table}"
        )

    connection.execute(
        text(
            f"CREATE UNIQUE INDEX {index_name} "
            f"ON {table} ({columns_sql}){where_sql}"
        )
    )
    inspector.clear_cache()


def _create_commission_transaction_index(connection, inspector) -> None:
    table = "balance_transactions"
    index_name = "uq_balance_tx_commission_reference"
    if not inspector.has_table(table):
        return

    indexes = inspector.get_indexes(table)
    if any(index.get("name") == index_name for index in indexes):
        return

    duplicate = connection.execute(
        text(
            "SELECT partner_id, reference_id, COUNT(*) "
            "FROM balance_transactions "
            "WHERE type = 'COMMISSION' AND reference_id IS NOT NULL "
            "GROUP BY partner_id, reference_id "
            "HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicate:
        raise RuntimeError(
            "Cannot create commission transaction idempotency index: "
            "duplicate balance transactions exist"
        )

    connection.execute(
        text(
            f"CREATE UNIQUE INDEX {index_name} "
            "ON balance_transactions (partner_id, reference_id) "
            "WHERE type = 'COMMISSION' AND reference_id IS NOT NULL"
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

        _create_commission_transaction_index(connection, inspector)
        _upgrade_postgresql_money_types(connection, inspector)

        if connection.dialect.name == "sqlite":
            for table, columns in _MONEY_COLUMNS.items():
                if not inspector.has_table(table):
                    continue
                if any(
                    isinstance(column["type"], Float)
                    for column in inspector.get_columns(table)
                    if column["name"] in columns
                ):
                    logger.warning(
                        "SQLite table %s has legacy floating-point money "
                        "columns; existing values need an offline table rebuild",
                        table,
                    )
