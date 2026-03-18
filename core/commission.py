import logging
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Tuple

from database.models import Commission, Purchase, Partner

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
    """
    MLM commission calculator (БЕЗ Telegram — чтобы не было timeout)
    """

    LEVEL_RATES = [
        Decimal("0.20"),
        Decimal("0.10"),
        Decimal("0.05"),
        Decimal("0.05"),
        Decimal("0.05"),
    ]

    def __init__(self, db):
        self.db = db

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

            if not is_active:
                commissions.append(
                    CommissionResult(
                        partner_id=partner_id,
                        level=level,
                        rate=rate,
                        base_amount=purchase_amount,
                        amount=Decimal("0.00"),
                        compressed=True,
                        notes="Partner inactive"
                    )
                )
                continue

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

        if purchase.is_commission_processed:
            return

        partner = (
            self.db.query(Partner)
            .filter(Partner.id == purchase.partner_id)
            .first()
        )

        if not partner:
            return

        lineage = partner.lineage or []
        upline_chain = [(pid, True) for pid in reversed(lineage)]

        results = self.calculate_purchase_commissions(
            purchase_amount=Decimal(str(purchase.amount)),
            buying_partner_id=partner.id,
            upline_chain=upline_chain
        )

        for res in results:

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

        purchase.is_commission_processed = True

        self.db.commit()