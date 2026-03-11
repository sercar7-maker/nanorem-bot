from database.db import SessionLocal
from database.models import Partner, Commission
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

        for p in partners:

            if not p.lineage:
                continue

            if partner_id in p.lineage:

                level = p.lineage.index(partner_id) + 1

                if level <= 5:
                    levels[level] += 1

        return levels

    def get_partner_stats(self, partner_id: int):

        session = SessionLocal()

        # Количество партнёров в сети
        partners = session.query(Partner).all()

        total_partners = 0

        for p in partners:
            if p.lineage and partner_id in p.lineage:
                total_partners += 1

        # Общая сумма комиссий
        total_commission = session.query(
            func.coalesce(func.sum(Commission.amount), 0)
        ).filter(
            Commission.partner_id == partner_id
        ).scalar()

        session.close()

        return {
            "partners": total_partners,
            "commission": float(total_commission)
        }