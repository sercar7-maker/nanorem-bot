from sqlalchemy.orm import Session

from database.models_stats import PartnerStats


class RankService:

    RANKS = [
        ("Diamond", 500_000),
        ("Platinum", 100_000),
        ("Gold", 50_000),
        ("Silver", 10_000),
        ("Partner", 0),
    ]

    def __init__(self, session: Session):
        self.session = session

    # -------------------------------------------------
    # Get rank by turnover
    # -------------------------------------------------

    def calculate_rank(self, partner_id: int) -> str:

        stats = (
            self.session.query(PartnerStats)
            .filter(PartnerStats.partner_id == partner_id)
            .first()
        )

        if not stats:
            return "Partner"

        turnover = stats.network_turnover or 0

        for rank_name, required_turnover in self.RANKS:
            if turnover >= required_turnover:
                return rank_name

        return "Partner"