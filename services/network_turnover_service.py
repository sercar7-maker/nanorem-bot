from sqlalchemy.orm import Session

from database.models_stats import PartnerStats


class NetworkTurnoverService:

    def __init__(self, session: Session):
        self.session = session

    # ----------------------------------------
    # Personal turnover (all time)
    # ----------------------------------------

    def get_personal_turnover(self, partner_id: int) -> float:

        stats = (
            self.session.query(PartnerStats)
            .filter(PartnerStats.partner_id == partner_id)
            .first()
        )

        if not stats:
            return 0.0

        return float(stats.personal_turnover)

    # ----------------------------------------
    # Personal turnover (monthly)
    # ----------------------------------------

    def get_monthly_personal_turnover(self, partner_id: int) -> float:

        stats = (
            self.session.query(PartnerStats)
            .filter(PartnerStats.partner_id == partner_id)
            .first()
        )

        if not stats:
            return 0.0

        return float(stats.monthly_personal_turnover)

    # ----------------------------------------
    # Network turnover (all time)
    # ----------------------------------------

    def get_network_turnover(self, partner_id: int) -> float:

        stats = (
            self.session.query(PartnerStats)
            .filter(PartnerStats.partner_id == partner_id)
            .first()
        )

        if not stats:
            return 0.0

        return float(stats.network_turnover)

    # ----------------------------------------
    # Network turnover (monthly)
    # ----------------------------------------

    def get_monthly_network_turnover(self, partner_id: int) -> float:

        stats = (
            self.session.query(PartnerStats)
            .filter(PartnerStats.partner_id == partner_id)
            .first()
        )

        if not stats:
            return 0.0

        return float(stats.monthly_network_turnover)

    # ----------------------------------------
    # Team size
    # ----------------------------------------

    def get_team_size(self, partner_id: int) -> int:

        stats = (
            self.session.query(PartnerStats)
            .filter(PartnerStats.partner_id == partner_id)
            .first()
        )

        if not stats:
            return 0

        return stats.team_size