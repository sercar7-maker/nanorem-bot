from database.models import Partner


class DistributionService:

    def get_upline_for_new_partner(self, session):
        """
        Выбираем, к кому прикрепить нового партнёра
        """

        roots = session.query(Partner).filter(
            Partner.upline_id == None
        ).all()

        if len(roots) < 2:
            raise Exception("Нужно минимум 2 root-партнёра")

        # считаем количество прямых партнёров
        counts = {}

        for root in roots:
            count = session.query(Partner).filter(
                Partner.upline_id == root.id
            ).count()

            counts[root.id] = count

        # выбираем у кого меньше
        selected_root_id = min(counts, key=counts.get)

        return selected_root_id