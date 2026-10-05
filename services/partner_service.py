from database.db import SessionLocal
from database.models import Partner, Commission, Purchase
from database.models_stats import PartnerStats
from sqlalchemy import func
from collections import deque


class PartnerService:

    # =========================
    # рџЋЇ Р’С‹Р±РѕСЂ root РїРѕ СЂР°Р·РјРµСЂСѓ СЃРµС‚Рё
    # =========================
    def choose_root(self, session):
        from services.distribution_service import DistributionService

        return DistributionService().get_upline_for_new_partner(session)
    # =========================
    # рџ‘¤ РЎРѕР·РґР°РЅРёРµ РїР°СЂС‚РЅС‘СЂР°
    # =========================
    def create_partner(self, telegram_id: str, upline_id: int = None):
        session = SessionLocal()

        try:
            existing_count = session.query(Partner).count()

            if existing_count < 2:
                upline_id = None
            elif not upline_id:
                upline_id = self.choose_root(session)

            lineage = []

            if upline_id:
                upline = session.query(Partner).filter(
                    Partner.id == upline_id
                ).first()

                if upline:
                    lineage = list(upline.lineage or [])
                    lineage.insert(0, upline.id)

            partner = Partner(
                telegram_id=telegram_id,
                upline_id=upline_id,
                lineage=lineage,
                status="ACTIVE",
                role="partner",
                rank="Partner"
            )

            session.add(partner)
            session.commit()
            session.refresh(partner)

            # рџ”Ґ РќРћР’РћР•: РћР±РЅРѕРІР»СЏРµРј team_size Сѓ РІСЃРµС… РїСЂРµРґРєРѕРІ
            for upline_id in lineage:
                stats = session.query(PartnerStats).filter(
                    PartnerStats.partner_id == upline_id
                ).first()
                
                if not stats:
                    stats = PartnerStats(
                        partner_id=upline_id,
                        personal_turnover=0,
                        network_turnover=0,
                        monthly_personal_turnover=0,
                        monthly_network_turnover=0,
                        team_size=0
                    )
                    session.add(stats)
                    session.flush()
                
                stats.team_size += 1
            
            session.commit()

            print(f"вњ… CREATED partner {partner.id} with lineage {partner.lineage}")

            return partner

        finally:
            session.close()

    # =========================
    # рџ”Ќ РџРѕР»СѓС‡РµРЅРёРµ РїР°СЂС‚РЅС‘СЂР°
    # =========================
    def get_partner_by_telegram_id(self, telegram_id: int):
        session = SessionLocal()

        partner = session.query(Partner).filter(
            Partner.telegram_id == telegram_id
        ).first()

        session.close()
        return partner

    # =========================
    # рџ’° Р‘Р°Р»Р°РЅСЃ
    # =========================
    def get_partner_balance(self, partner_id: int):
        session = SessionLocal()

        balance = session.query(
            func.coalesce(func.sum(Commission.amount), 0)
        ).filter(
            Commission.partner_id == partner_id
        ).scalar()

        session.close()
        return balance

    # =========================
    # рџЊі РЎРµС‚СЊ (СѓСЂРѕРІРЅРё)
    # =========================
    def get_network_levels(self, partner_id: int):
        session = SessionLocal()

        levels = {
            1: 0,
            2: 0,
            3: 0,
            4: 0,
            5: 0
        }

        try:
            level_1 = session.query(Partner).filter(
                Partner.upline_id == partner_id
            ).all()

            levels[1] = len(level_1)

            level_1_ids = [p.id for p in level_1]

            level_2 = []
            if level_1_ids:
                level_2 = session.query(Partner).filter(
                    Partner.upline_id.in_(level_1_ids)
                ).all()
                levels[2] = len(level_2)

            level_2_ids = [p.id for p in level_2]

            level_3 = []
            if level_2_ids:
                level_3 = session.query(Partner).filter(
                    Partner.upline_id.in_(level_2_ids)
                ).all()
                levels[3] = len(level_3)

            level_3_ids = [p.id for p in level_3]

            level_4 = []
            if level_3_ids:
                level_4 = session.query(Partner).filter(
                    Partner.upline_id.in_(level_3_ids)
                ).all()
                levels[4] = len(level_4)

            level_4_ids = [p.id for p in level_4]

            if level_4_ids:
                level_5 = session.query(Partner).filter(
                    Partner.upline_id.in_(level_4_ids)
                ).all()
                levels[5] = len(level_5)

            levels["total"] = (
                levels[1] + levels[2] + levels[3] + levels[4] + levels[5]
            )

            return levels

        finally:
            session.close()

    # =========================
    # рџЊђ ID РІСЃРµР№ СЃРµС‚Рё
    # =========================
    def get_network_partner_ids(self, partner_id: int, session):
        all_ids = []

        level_ids = [partner_id]

        for _ in range(5):
            partners = session.query(Partner).filter(
                Partner.upline_id.in_(level_ids)
            ).all()

            level_ids = [p.id for p in partners]

            if not level_ids:
                break

            all_ids.extend(level_ids)

        return all_ids

    # =========================
    # рџ“Љ РЎС‚Р°С‚РёСЃС‚РёРєР°
    # =========================
    def get_partner_stats(self, partner_id: int):
        session = SessionLocal()

        try:
            network_ids = self.get_network_partner_ids(partner_id, session)

            total_partners = len(network_ids)

            total_commission = session.query(
                func.coalesce(func.sum(Commission.amount), 0)
            ).filter(
                Commission.partner_id == partner_id
            ).scalar()

            personal_turnover = session.query(
                func.coalesce(func.sum(Purchase.amount), 0)
            ).filter(
                Purchase.partner_id == partner_id
            ).scalar()

            network_turnover = 0.0

            if network_ids:
                network_turnover = session.query(
                    func.coalesce(func.sum(Purchase.amount), 0)
                ).filter(
                    Purchase.partner_id.in_(network_ids)
                ).scalar()

            return {
                "partners": total_partners,
                "commission": float(total_commission),
                "personal_turnover": float(personal_turnover),
                "network_turnover": float(network_turnover),
            }

        finally:
            session.close()
