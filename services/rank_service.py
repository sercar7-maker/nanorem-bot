from database.models import Partner
from services.stats_service import StatsService


class RankService:

    RANKS = [
        ("Partner", 0),
        ("Silver", 10000),
        ("Gold", 50000),
        ("Platinum", 100000),
    ]

    @staticmethod
    def calculate_rank(personal_turnover: float) -> str:

        current_rank = "Partner"

        for rank, threshold in RankService.RANKS:
            if personal_turnover >= threshold:
                current_rank = rank

        return current_rank

    @staticmethod
    def update_partner_rank(session, partner, new_rank: str):

        if partner.rank != new_rank:
            old_rank = partner.rank
            partner.rank = new_rank
            session.commit()
            return old_rank, new_rank

        return None, None

    @staticmethod
    def process_rank(session, partner):

        stats_service = StatsService(session)

        stats = stats_service.get_or_create_stats(partner.id)

        new_rank = RankService.calculate_rank(stats.personal_turnover)

        old_rank, updated_rank = RankService.update_partner_rank(
            session, partner, new_rank
        )

        return old_rank, updated_rank