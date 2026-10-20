
import logging
import re

from sqlalchemy import Float, Engine, inspect, text
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from database.models import (
    AuthChallenge,
    AuthSession,
    PartnerRecoveryChild,
    PartnerRecoveryEvent,
    RootAllocationLock,
    create_referral_code,
)
from database.models_balance import BalanceOrderReservation


logger = logging.getLogger(__name__)

_UNIQUE_INDEXES = (
    (
        "partners",
        "uq_partners_referral_code",
        ("referral_code",),
        None,
    ),
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
    (
        "balance_transactions",
        "uq_balance_tx_purchase_external_id",
        ("partner_id", "external_id"),
        "type = 'PURCHASE_PAYMENT' AND external_id IS NOT NULL",
    ),
    (
        "balance_order_reservations",
        "uq_balance_order_reservations_order_id",
        ("order_id",),
        None,
    ),
    (
        "withdrawals",
        "uq_withdrawals_partner_request_id",
        ("partner_id", "request_id"),
        "request_id IS NOT NULL",
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


def _ensure_partner_activity_columns(connection, inspector) -> None:
    if not inspector.has_table("partners"):
        return

    present = {
        column["name"] for column in inspector.get_columns("partners")
    }
    if "annual_activity_until" in present:
        return

    column_type = (
        "DATETIME"
        if connection.dialect.name == "sqlite"
        else "TIMESTAMP"
    )
    connection.execute(
        text(
            "ALTER TABLE partners "
            f"ADD COLUMN annual_activity_until {column_type}"
        )
    )
    inspector.clear_cache()


def _ensure_partner_referral_codes(connection, inspector) -> None:
    if not inspector.has_table("partners"):
        return

    columns = {
        column["name"] for column in inspector.get_columns("partners")
    }
    if "referral_code" not in columns:
        connection.execute(
            text("ALTER TABLE partners ADD COLUMN referral_code VARCHAR(32)")
        )
        inspector.clear_cache()

    rows = connection.execute(
        text(
            "SELECT id, referral_code FROM partners "
            "ORDER BY id"
        )
    ).mappings().all()
    used_codes: set[str] = set()

    for row in rows:
        current_code = row["referral_code"]
        if (
            current_code
            and current_code.startswith("nr_")
            and current_code not in used_codes
        ):
            used_codes.add(current_code)
            continue

        new_code = create_referral_code()
        while new_code in used_codes:
            new_code = create_referral_code()
        connection.execute(
            text(
                "UPDATE partners SET referral_code = :referral_code "
                "WHERE id = :partner_id"
            ),
            {
                "referral_code": new_code,
                "partner_id": row["id"],
            },
        )
        used_codes.add(new_code)

    inspector.clear_cache()


def _ensure_partner_placement_columns(connection, inspector) -> None:
    if not inspector.has_table("partners"):
        return

    present = {
        column["name"] for column in inspector.get_columns("partners")
    }
    definitions = {
        "upline_id": "INTEGER REFERENCES partners(id)",
        "root_id": "INTEGER REFERENCES partners(id)",
        "placement_version": "INTEGER NOT NULL DEFAULT 0",
    }
    for name, definition in definitions.items():
        if name not in present:
            connection.execute(
                text(
                    f"ALTER TABLE partners "
                    f"ADD COLUMN {name} {definition}"
                )
            )
            inspector.clear_cache()

    rows = connection.execute(
        text("SELECT id, upline_id, root_id FROM partners")
    ).mappings().all()
    parents = {row["id"]: row["upline_id"] for row in rows}
    existing_roots = {row["id"]: row["root_id"] for row in rows}
    resolved_roots: dict[int, int] = {}

    for partner_id, existing_root in existing_roots.items():
        if existing_root is not None:
            if existing_root not in parents:
                raise RuntimeError(
                    f"Partner {partner_id} references missing root "
                    f"{existing_root}; placement migration stopped"
                )
            resolved_roots[partner_id] = existing_root
            continue

        current_id = partner_id
        visited = set()
        while parents[current_id] is not None:
            if current_id in visited:
                raise RuntimeError(
                    f"Cycle detected in partner placement at ID "
                    f"{current_id}; placement migration stopped"
                )
            visited.add(current_id)
            parent_id = parents[current_id]
            if parent_id not in parents:
                raise RuntimeError(
                    f"Partner {current_id} references missing parent "
                    f"{parent_id}; placement migration stopped"
                )
            if parent_id in resolved_roots:
                current_id = resolved_roots[parent_id]
                break
            current_id = parent_id

        if current_id not in parents:
            raise RuntimeError(
                f"Could not resolve root for partner {partner_id}; "
                "placement migration stopped"
            )
        resolved_roots[partner_id] = (
            existing_roots.get(current_id) or current_id
        )

    for partner_id, root_id in resolved_roots.items():
        if existing_roots[partner_id] != root_id:
            connection.execute(
                text(
                    "UPDATE partners SET root_id = :root_id "
                    "WHERE id = :partner_id"
                ),
                {"root_id": root_id, "partner_id": partner_id},
            )


def _ensure_root_allocation_lock(connection) -> None:
    RootAllocationLock.__table__.create(connection, checkfirst=True)
    inspector = inspect(connection)

    columns = {
        column["name"]
        for column in inspector.get_columns("root_allocation_lock")
    }
    primary_key_columns = inspector.get_pk_constraint(
        "root_allocation_lock"
    ).get("constrained_columns") or []
    if not {"id", "lock_version"}.issubset(columns) or (
        primary_key_columns != ["id"]
    ):
        raise RuntimeError(
            "The root allocation lock table has an unexpected schema; "
            "inspect it manually before continuing"
        )

    insert = (
        sqlite_insert
        if connection.dialect.name == "sqlite"
        else postgresql_insert
        if connection.dialect.name == "postgresql"
        else None
    )
    if insert is None:
        raise RuntimeError(
            "Root allocation locking is supported only on SQLite and PostgreSQL"
        )

    connection.execute(
        insert(RootAllocationLock.__table__)
        .values(id=1, lock_version=0)
        .on_conflict_do_nothing(index_elements=["id"])
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


def _ensure_partner_email_index(connection, inspector) -> None:
    table = "partners"
    index_name = "uq_partners_email_normalized"
    if not inspector.has_table(table):
        return

    columns = {
        column["name"] for column in inspector.get_columns(table)
    }
    if "email" not in columns:
        return

    if connection.dialect.name == "sqlite":
        index_sql = connection.execute(
            text(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'index' AND name = :index_name"
            ),
            {"index_name": index_name},
        ).scalar_one_or_none()
    elif connection.dialect.name == "postgresql":
        index_sql = connection.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = current_schema() "
                "AND tablename = :table AND indexname = :index_name"
            ),
            {"table": table, "index_name": index_name},
        ).scalar_one_or_none()
    else:
        raise RuntimeError(
            "Case-insensitive partner email uniqueness is supported only "
            "on SQLite and PostgreSQL"
        )

    if index_sql:
        normalized_sql = re.sub(
            r'[\s"\[\]`]', "", index_sql
        ).lower()
        if (
            "createuniqueindex" not in normalized_sql
            or "lower(" not in normalized_sql
            or not re.search(
                r"lower\(\(*(?:partners\.)?email",
                normalized_sql,
            )
        ):
            raise RuntimeError(
                f"Cannot apply {index_name}: an index with that name exists "
                "but does not enforce case-insensitive email uniqueness"
            )
        return

    duplicate = connection.execute(
        text(
            "SELECT lower(email), COUNT(*) FROM partners "
            "WHERE email IS NOT NULL "
            "GROUP BY lower(email) HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicate:
        raise RuntimeError(
            "Cannot create uq_partners_email_normalized: duplicate rows "
            "exist in partners for case-insensitive email. Diagnose with: "
            "SELECT lower(email), COUNT(*) FROM partners "
            "WHERE email IS NOT NULL GROUP BY lower(email) "
            "HAVING COUNT(*) > 1"
        )

    connection.execute(
        text(
            f"CREATE UNIQUE INDEX {index_name} "
            "ON partners (lower(email))"
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


def _ensure_withdrawal_processor_permission(connection, inspector) -> None:
    if not inspector.has_table("partners"):
        return

    present = {
        column["name"] for column in inspector.get_columns("partners")
    }
    if "can_process_withdrawals" in present:
        return

    if connection.dialect.name not in {"sqlite", "postgresql"}:
        raise RuntimeError(
            "Withdrawal processing permission is supported only "
            "on SQLite and PostgreSQL"
        )

    boolean_default = (
        "0" if connection.dialect.name == "sqlite" else "FALSE"
    )
    connection.execute(
        text(
            "ALTER TABLE partners ADD COLUMN "
            "can_process_withdrawals "
            f"BOOLEAN NOT NULL DEFAULT {boolean_default}"
        )
    )
    inspector.clear_cache()


def _ensure_withdrawal_request_id(connection, inspector) -> None:
    if not inspector.has_table("withdrawals"):
        return

    present = {
        column["name"] for column in inspector.get_columns("withdrawals")
    }
    if "request_id" in present:
        return

    if connection.dialect.name not in {"sqlite", "postgresql"}:
        raise RuntimeError(
            "Withdrawal request_id migration is supported only "
            "on SQLite and PostgreSQL"
        )

    connection.execute(
        text(
            "ALTER TABLE withdrawals "
            "ADD COLUMN request_id VARCHAR(36)"
        )
    )
    inspector.clear_cache()


def upgrade_schema(engine: Engine) -> None:
    """Apply safe, additive upgrades for schemas created before these models."""
    with engine.begin() as connection:
        inspector = inspect(connection)
        _ensure_partner_placement_columns(connection, inspector)
        PartnerRecoveryEvent.__table__.create(
            connection,
            checkfirst=True,
        )
        PartnerRecoveryChild.__table__.create(
            connection,
            checkfirst=True,
        )
        AuthChallenge.__table__.create(connection, checkfirst=True)
        AuthSession.__table__.create(connection, checkfirst=True)
        _ensure_root_allocation_lock(connection)
        BalanceOrderReservation.__table__.create(
            connection,
            checkfirst=True,
        )
        inspector.clear_cache()
        _add_consent_columns(connection, inspector)
        _ensure_partner_activity_columns(connection, inspector)
        _ensure_partner_referral_codes(connection, inspector)
        _ensure_withdrawal_processor_permission(connection, inspector)
        _ensure_withdrawal_request_id(connection, inspector)

        for table, index_name, columns, predicate in _UNIQUE_INDEXES:
            _create_unique_index(
                connection,
                inspector,
                table,
                index_name,
                columns,
                predicate,
            )

        _ensure_partner_email_index(connection, inspector)

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
