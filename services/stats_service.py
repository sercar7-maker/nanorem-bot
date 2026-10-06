from sqlalchemy.orm import Session
from decimal import Decimal

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
                personal_turnover=Decimal("0.00"),
                network_turnover=Decimal("0.00"),
                monthly_personal_turnover=Decimal("0.00"),
                monthly_network_turnover=Decimal("0.00"),
            )
            self.session.add(stats)
            self.session.flush()

        return stats

    def add_personal_turnover(self, partner_id: int, amount: Decimal):

        stats = self._get_or_create_stats(partner_id)

        stats.personal_turnover += amount
        stats.monthly_personal_turnover += amount

    def add_network_turnover(self, partner_id: int, amount: Decimal):

        stats = self._get_or_create_stats(partner_id)

        stats.network_turnover += amount
        stats.monthly_network_turnover += amount

    def process_purchase(self, partner_id: int, amount: Decimal):

        partner = (
            self.session.query(Partner)
            .filter(Partner.id == partner_id)
            .first()
        )

        if not partner:
            raise ValueError(f"Партнёр {partner_id} не найден")

        # -------------------------------------------------
        # ЛИЧНЫЙ ОБОРОТ
        # -------------------------------------------------

        self.add_personal_turnover(partner_id, amount)

        # -------------------------------------------------
        # СЕТЕВОЙ ОБОРОТ (через lineage)
        # -------------------------------------------------

        lineage = partner.lineage or []

        for upline_id in dict.fromkeys(lineage):
            if upline_id == partner_id:
                continue
            self.add_network_turnover(upline_id, amount)

        return self._get_or_create_stats(partner_id)