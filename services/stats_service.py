from sqlalchemy.orm import Session
from datetime import datetime

from database.models import Partner
from database.models_stats import PartnerStats


class StatsService:

    def __init__(self, session: Session):
        self.session = session

    def _get_or_create_stats(self, partner_id: int) -> PartnerStats:

        stats = (
            self.session.query(PartnerStats)
            .filter(PartnerStats.partner_id == partner_id)
            .first()
        )

        if not stats:
            stats = PartnerStats(
                partner_id=partner_id,
                personal_turnover=0,
                network_turnover=0,
                monthly_personal_turnover=0,
                monthly_network_turnover=0,
            )
            self.session.add(stats)
            self.session.flush()

        return stats

    def add_personal_turnover(self, partner_id: int, amount: float):

        stats = self._get_or_create_stats(partner_id)

        stats.personal_turnover += amount
        stats.monthly_personal_turnover += amount

    def add_network_turnover(self, partner_id: int, amount: float):

        stats = self._get_or_create_stats(partner_id)

        stats.network_turnover += amount
        stats.monthly_network_turnover += amount

    def process_purchase(self, partner_id: int, amount: float):

        partner = (
            self.session.query(Partner)
            .filter(Partner.id == partner_id)
            .first()
        )

        if not partner:
            return

        # -------------------------------------------------
        # ЛИЧНЫЙ ОБОРОТ
        # -------------------------------------------------

        self.add_personal_turnover(partner_id, amount)

        # -------------------------------------------------
        # СЕТЕВОЙ ОБОРОТ (через lineage)
        # -------------------------------------------------

        lineage = partner.lineage or []

        for upline_id in lineage:
            self.add_network_turnover(upline_id, amount)

        # -------------------------------------------------
        # ✅ ФИКСИРУЕМ В БД
        # -------------------------------------------------

        self.session.commit()