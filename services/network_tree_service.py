from sqlalchemy.orm import Session
from database.models import Partner


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
            .filter(Partner.lineage.contains([partner_id]))
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