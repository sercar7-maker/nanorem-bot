import logging
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Tuple

from database.models import Commission, Purchase, Partner
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

    def calculate_purchase_commissions(
        self,
        purchase_amount: Decimal,
        buying_partner_id: int,
        upline_chain: List[Tuple[int, bool]]
    ) -> List[CommissionResult]:

        commissions: List[CommissionResult] = []

        for level, (partner_id, is_active) in enumerate(upline_chain, start=1):

            if level > len(self.LEVEL_RATES):
                break

            rate = self.LEVEL_RATES[level - 1]

            amount = (purchase_amount * rate).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

            commissions.append(
                CommissionResult(
                    partner_id=partner_id,
                    level=level,
                    rate=rate,
                    base_amount=purchase_amount,
                    amount=amount
                )
            )

        return commissions

    async def process_purchase(self, purchase: Purchase):

        print("🚀 PROCESS PURCHASE CALLED")

        # 🔒 ЗАЩИТА ОТ ДУБЛЕЙ
        if purchase.is_commission_processed:
            print("⛔ commissions already processed")
            return

        partner = (
            self.db.query(Partner)
            .filter(Partner.id == purchase.partner_id)
            .first()
        )

        if not partner:
            print("❌ partner not found")
            return

        lineage = partner.lineage or []

        print(f"🌳 LINEAGE: {lineage}")

        upline_chain = [(pid, True) for pid in lineage]

        results = self.calculate_purchase_commissions(
            purchase_amount=Decimal(str(purchase.amount)),
            buying_partner_id=partner.id,
            upline_chain=upline_chain
        )

        print(f"📊 RESULTS: {results}")

        for res in results:

            print(f"💾 ADD commission {res.amount} to {res.partner_id}")

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

            # 🔔 НОВОЕ: Отправляем уведомление получателю комиссии
            if self.notify and self.notify.bot:
                try:
                    # Получаем telegram_id получателя
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
                    print(f"⚠️ Failed to send notification: {e}")

        purchase.is_commission_processed = True

        self.db.commit()

        print("✅ DONE")