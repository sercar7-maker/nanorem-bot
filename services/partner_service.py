from database.db import SessionLocal
from database.models import Partner, Commission, Purchase
from database.models_balance import Balance
from database.models_stats import PartnerStats
from sqlalchemy import func, or_
from collections import deque
from datetime import datetime
from services.root_allocation_lock import acquire_root_allocation_lock
from services.structural_compression_service import (
    StructuralCompressionService,
)


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
    def create_partner(
        self,
        telegram_id: str | None,
        upline_id: int | None = None,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        telegram_link_code: str | None = None,
        consent_given: bool = False,
        consent_version: str | None = None,
        consent_date: datetime | None = None,
    ):
        session = SessionLocal()

        try:
            acquire_root_allocation_lock(session)
            if email:
                email = email.strip().lower()

            root_count = session.query(Partner).filter(
                Partner.upline_id.is_(None),
                or_(
                    Partner.root_id.is_(None),
                    Partner.root_id == Partner.id,
                ),
            ).count()
            if root_count != 2:
                raise ValueError(
                    "System is not ready for registration: exactly two "
                    "Root partners must be created by an administrator"
                )

            if upline_id is None:
                raise ValueError("A referral link is required")

            lineage = []

            upline = session.query(Partner).filter(
                Partner.id == upline_id
            ).first()

            if not upline:
                raise ValueError("Referral partner not found")

            lineage = list(upline.lineage or [])
            lineage.insert(0, upline.id)

            partner = Partner(
                telegram_id=telegram_id,
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                upline_id=upline_id,
                lineage=lineage,
                telegram_link_code=telegram_link_code,
                consent_given=consent_given,
                consent_version=consent_version,
                consent_date=consent_date,
                status="ACTIVE",
                role="partner",
                rank="Partner"
            )

            session.add(partner)
            session.flush()
            StructuralCompressionService(
                session
            ).ensure_root_affiliation(partner)
            session.flush()

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
            session.refresh(partner)

            print(f"вњ… CREATED partner {partner.id} with lineage {partner.lineage}")

            return partner

        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create_root(
        self,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
    ):
        session = SessionLocal()

        try:
            acquire_root_allocation_lock(session)
            root_count = session.query(Partner).filter(
                Partner.upline_id.is_(None),
                or_(
                    Partner.root_id.is_(None),
                    Partner.root_id == Partner.id,
                ),
            ).count()
            if root_count >= 2:
                raise ValueError("The system already has two Root partners")

            partner = Partner(
                first_name=first_name,
                last_name=last_name,
                email=email.strip().lower() if email else None,
                phone=phone,
                upline_id=None,
                lineage=[],
                subscription_end_date=None,
                status="ACTIVE",
                role="partner",
                rank="Partner",
            )
            session.add(partner)
            session.flush()
            partner.root_id = partner.id
            session.flush()
            session.commit()
            session.refresh(partner)
            return partner
        except Exception:
            session.rollback()
            raise
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

        try:
            balance = session.query(Balance.amount).filter(
                Balance.partner_id == partner_id
            ).scalar()

            if balance is not None:
                return balance

            # Legacy accounts may have commissions but no balance row.
            return session.query(
                func.coalesce(func.sum(Commission.amount), 0)
            ).filter(
                Commission.partner_id == partner_id
            ).scalar()
        finally:
            session.close()

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
            frontier = [partner_id]
            visited = {partner_id}
            depth = 0
            total = 0

            while frontier:
                children = session.query(Partner).filter(
                    Partner.upline_id.in_(frontier)
                ).all()
                frontier = [
                    child.id
                    for child in children
                    if child.id not in visited
                ]
                if not frontier:
                    break

                visited.update(frontier)
                depth += 1
                total += len(frontier)
                if depth <= 5:
                    levels[depth] = len(frontier)

            levels["total"] = total

            return levels

        finally:
            session.close()

    # =========================
    # рџЊђ ID РІСЃРµР№ СЃРµС‚Рё
    # =========================
    def get_network_partner_ids(self, partner_id: int, session):
        all_ids = []

        level_ids = [partner_id]
        visited = {partner_id}

        while level_ids:
            partners = session.query(Partner).filter(
                Partner.upline_id.in_(level_ids)
            ).all()

            level_ids = [
                partner.id
                for partner in partners
                if partner.id not in visited
            ]
            visited.update(level_ids)
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
