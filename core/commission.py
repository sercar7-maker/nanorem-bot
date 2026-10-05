import logging
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Tuple, Optional


from database.models import Commission, Purchase, Partner, PartnerStatus
from services.notifications import NotificationService
from services.commission_service import CommissionService


logger = logging.getLogger(__name__)



@dataclass
class CommissionResult:
    partner_id: int
    level: int
    rate: Decimal
    base_amount: Decimal
    amount: Decimal
    compressed: bool = False
    notes: str = ""



class CommissionCalculator:


    LEVEL_RATES = [
        Decimal("0.20"),
        Decimal("0.10"),
        Decimal("0.05"),
        Decimal("0.05"),
        Decimal("0.05"),
    ]


    def __init__(self, db, bot):
        self.db = db
        self.notify = NotificationService(bot)
        self.commission_service = CommissionService(db)


    def _get_partner_is_active(self, partner_id: int) -> bool:
        """РџСЂРѕРІРµСЂСЏРµС‚, Р°РєС‚РёРІРµРЅ Р»Рё РїР°СЂС‚РЅС‘СЂ (РјРѕР¶РЅРѕ РєСЌС€РёСЂРѕРІР°С‚СЊ, РµСЃР»Рё РЅСѓР¶РЅРѕ)."""
        partner = (
            self.db.query(Partner)
            .filter(Partner.id == partner_id)
            .first()
        )
        if not partner:
            return False
        # РџСЂРµРґРїРѕР»Р°РіР°РµРј, С‡С‚Рѕ РІ РјРѕРґРµР»Рё Partner РµСЃС‚СЊ РїРѕР»Рµ is_active
        return partner.status == PartnerStatus.ACTIVE


    def _build_compressed_chain(
        self,
        lineage: List[int],
        max_levels: int = 5
    ) -> List[Tuple[int, int, bool]]:
        """
        ?????? ?????? ??????? ???????? ????????.

        ????????? ???????? ????????????.
        ????????? ???????? ??????? ???????? ?????????????? ???????.
        """

        compressed_chain: List[Tuple[int, int, bool]] = []
        level = 0
        skipped_inactive = False

        for partner_id in lineage:
            if level >= max_levels:
                break

            if not self._get_partner_is_active(partner_id):
                skipped_inactive = True
                continue

            level += 1

            compressed_chain.append(
                (
                    partner_id,
                    level,
                    skipped_inactive,
                )
            )

        return compressed_chain

    def calculate_purchase_commissions(
        self,
        purchase_amount: Decimal,
        buying_partner_id: int,
        lineage: List[int]
    ) -> List[CommissionResult]:


        commissions: List[CommissionResult] = []

        # РЎС‚СЂРѕРёРј СЃР¶Р°С‚СѓСЋ С†РµРїРѕС‡РєСѓ Р°РєС‚РёРІРЅС‹С… Р°РїР»Р°Р№РЅРѕРІ
        compressed_chain = self._build_compressed_chain(lineage, max_levels=5)

        for partner_id, level, is_compressed in compressed_chain:
            if level > len(self.LEVEL_RATES):
                break

            rate = self.LEVEL_RATES[level - 1]

            amount = (purchase_amount * rate).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

            notes = ""
            if is_compressed:
                notes = "compressed_up"

            commissions.append(
                CommissionResult(
                    partner_id=partner_id,
                    level=level,
                    rate=rate,
                    base_amount=purchase_amount,
                    amount=amount,
                    compressed=is_compressed,
                    notes=notes,
                )
            )

        return commissions


    async def process_purchase(self, purchase: Purchase):


        print("рџљЂ PROCESS PURCHASE CALLED")
        # рџ”’ Р—РђР©РРўРђ РћРў Р”РЈР‘Р›Р•Р™
        if purchase.is_commission_processed:
            print("в›” commissions already processed")
            return


        partner = (
            self.db.query(Partner)
            .filter(Partner.id == purchase.partner_id)
            .first()
        )


        if not partner:
            print("вќЊ partner not found")
            return


        lineage = partner.lineage or []
        print(f"рџЊі LINEAGE: {lineage}")

        # рџ”Ґ РќРћР’РћР•: РёСЃРїРѕР»СЊР·СѓРµРј lineage РЅР°РїСЂСЏРјСѓСЋ, РєРѕРјРїСЂРµСЃСЃРёСЏ РІРЅСѓС‚СЂРё calculate
        results = self.calculate_purchase_commissions(
            purchase_amount=Decimal(str(purchase.amount)),
            buying_partner_id=partner.id,
            lineage=lineage,
        )


        print(f"рџ“Љ RESULTS: {results}")


        for res in results:


            print(f"рџ’ѕ ADD commission {res.amount} to {res.partner_id}")
            commission = Commission(
                partner_id=res.partner_id,
                purchase_id=purchase.id,
                source_partner_id=partner.id,
                level=res.level,
                rate=float(res.rate),
                base_amount=float(res.base_amount),
                amount=float(res.amount),
                is_compressed=res.compressed,
                notes=res.notes,
            )


            self.db.add(commission)
            self.db.flush()


            self.commission_service.approve_commission(commission)


            # рџ”” РћС‚РїСЂР°РІР»СЏРµРј СѓРІРµРґРѕРјР»РµРЅРёРµ РїРѕР»СѓС‡Р°С‚РµР»СЋ РєРѕРјРёСЃСЃРёРё
            if self.notify and self.notify.bot:
                try:
                    recipient = self.db.query(Partner).filter(
                        Partner.id == res.partner_id
                    ).first()
                    
                    if recipient and recipient.telegram_id:
                        buyer_name = partner.first_name or partner.username or str(partner.id)
                        await self.notify.notify_commission(
                            telegram_id=int(recipient.telegram_id),
                            amount=float(res.amount),
                            level=res.level,
                            buyer_name=buyer_name
                        )
                except Exception as e:
                    print(f"вљ пёЏ Failed to send notification: {e}")


        purchase.is_commission_processed = True


        self.db.commit()


        print("вњ… DONE")
