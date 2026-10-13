from sqlalchemy import or_

from database.models import Partner


class DistributionService:
    def get_upline_for_new_partner(self, session):
        roots = (
            session.query(Partner)
            .filter(
                Partner.upline_id.is_(None),
                or_(
                    Partner.root_id.is_(None),
                    Partner.root_id == Partner.id,
                ),
            )
            .order_by(Partner.id)
            .all()
        )

        if len(roots) != 2:
            raise ValueError("Нужно ровно 2 root-партнёра")

        root_ids = {root.id: 0 for root in roots}

        # Не используем JSON.contains(), потому что SQLite
        # работает с ним ненадёжно для нашего поля lineage.
        partners = session.query(Partner.id, Partner.lineage).all()

        for _, lineage in partners:
            lineage = lineage or []

            for root_id in root_ids:
                if root_id in lineage:
                    root_ids[root_id] += 1

        # При равенстве выбирается root с большим ID (для балансировки)
        min_count = min(root_ids.values())
        candidates = [root_id for root_id, count in root_ids.items() if count == min_count]
        return max(candidates)