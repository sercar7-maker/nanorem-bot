from database.db import SessionLocal
from database.models import Partner, Commission
from database.models_stats import PartnerStats
from sqlalchemy import func


class PartnerService:

    def get_partner_by_telegram_id(self, telegram_id: int):

        session = SessionLocal()

        partner = session.query(Partner).filter(
            Partner.telegram_id == telegram_id
        ).first()

        session.close()

        return partner

    def get_partner_balance(self, partner_id: int):

        session = SessionLocal()

        balance = session.query(
            func.coalesce(func.sum(Commission.amount), 0)
        ).filter(
            Commission.partner_id == partner_id
        ).scalar()

        session.close()

        return balance

    def get_network_levels(self, partner_id: int):

        session = SessionLocal()

        partners = session.query(Partner).all()

        session.close()

        levels = {
            1: 0,
            2: 0,
            3: 0,
            4: 0,
            5: 0
        }

        total = 0

        for p in partners:

            if not p.lineage:
                continue

            if partner_id in p.lineage:

                level = p.lineage.index(partner_id) + 1

                if level <= 5:
                    levels[level] += 1
                    total += 1

        levels["total"] = total

        return levels

    def get_partner_stats(self, partner_id: int):

        session = SessionLocal()

        # -----------------------------
        # Партнёры в сети
        # -----------------------------
        partners = session.query(Partner).all()

        total_partners = 0

        for p in partners:
            if p.lineage and partner_id in p.lineage:
                total_partners += 1

        # -----------------------------
        # Комиссии
        # -----------------------------
        total_commission = session.query(
            func.coalesce(func.sum(Commission.amount), 0)
        ).filter(
            Commission.partner_id == partner_id
        ).scalar()

        # -----------------------------
        # Обороты
        # -----------------------------
        stats = session.query(PartnerStats).filter(
            PartnerStats.partner_id == partner_id
        ).first()

        personal_turnover = 0.0
        network_turnover = 0.0

        if stats:
            personal_turnover = stats.personal_turnover or 0.0
            network_turnover = stats.network_turnover or 0.0

        session.close()

        return {
            "partners": total_partners,
            "commission": float(total_commission),
            "personal_turnover": float(personal_turnover),
            "network_turnover": float(network_turnover),
        }