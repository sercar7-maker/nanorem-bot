from sqlalchemy import cast, exists, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from database.models import Partner


def _lineage_contains(partner_id: int, dialect_name: str):
    if dialect_name == "postgresql":
        return cast(Partner.lineage, JSONB).contains([partner_id])

    if dialect_name == "sqlite":
        lineage_item = func.json_each(
            Partner.lineage
        ).table_valued("key", "value")
        return exists(
            select(1)
            .select_from(lineage_item)
            .where(lineage_item.c.value == partner_id)
        )

    raise RuntimeError(
        f"Network lineage queries are not supported for {dialect_name}"
    )


class NetworkTreeService:

    def __init__(self, session: Session):
        self.session = session

    # -------------------------------------------------
    # Direct partners (1 level)
    # -------------------------------------------------

    def get_direct_partners(self, partner_id: int):

        partners = (
            self.session.query(Partner)
            .filter(Partner.upline_id == partner_id)
            .all()
        )

        result = []

        for p in partners:
            result.append({
                "id": p.id,
                "first_name": p.first_name,
                "username": p.username,
                "status": p.status.value if p.status else "unknown"
            })

        return result

    # -------------------------------------------------
    # Full network tree
    # -------------------------------------------------

    def get_network_tree(self, partner_id: int):
        partners = (
            self.session.query(Partner)
            .filter(
                _lineage_contains(
                    partner_id,
                    self.session.bind.dialect.name,
                )
            )
            .all()
        )

        tree = {}

        for p in partners:

            if p.upline_id not in tree:
                tree[p.upline_id] = []

            tree[p.upline_id].append({
                "id": p.id,
                "first_name": p.first_name,
                "username": p.username
            })

        return tree