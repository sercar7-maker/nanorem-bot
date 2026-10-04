from database.models import Partner


class DistributionService:
    def get_upline_for_new_partner(self, session):
        roots = (
            session.query(Partner)
            .filter(Partner.upline_id.is_(None))
            .order_by(Partner.id)
            .all()
        )

        if len(roots) < 2:
            raise ValueError("Нужно минимум 2 root-партнёра")

        # Берём первые два root-партнёра.
        roots = roots[:2]

        root_ids = {root.id: 0 for root in roots}

        # Не используем JSON.contains(), потому что SQLite
        # работает с ним ненадёжно для нашего поля lineage.
        partners = session.query(Partner.id, Partner.lineage).all()

        for _, lineage in partners:
            lineage = lineage or []

            for root_id in root_ids:
                if root_id in lineage:
                    root_ids[root_id] += 1

        # При равенстве выбирается первый root.
        return min(root_ids, key=root_ids.get)