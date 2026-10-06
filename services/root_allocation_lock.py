from sqlalchemy import select, update
from sqlalchemy.orm import Session

from database.models import RootAllocationLock


def acquire_root_allocation_lock(session: Session) -> None:
    """Serialize partner creation while roots/uplines are being assigned."""
    dialect_name = session.get_bind().dialect.name
    if dialect_name == "postgresql":
        lock_id = session.execute(
            select(RootAllocationLock.id)
            .where(RootAllocationLock.id == 1)
            .with_for_update()
        ).scalar_one_or_none()
        if lock_id == 1:
            return
    elif dialect_name == "sqlite":
        # SQLite has no row locks; this write serializes transactions before
        # they read the root count or choose a network.
        result = session.execute(
            update(RootAllocationLock)
            .where(RootAllocationLock.id == 1)
            .values(lock_version=RootAllocationLock.lock_version)
        )
        if result.rowcount == 1:
            return
    else:
        raise RuntimeError(
            "Root allocation locking is supported only on SQLite and PostgreSQL"
        )

    raise RuntimeError(
        "Root allocation lock is not initialized; run database migrations"
    )
