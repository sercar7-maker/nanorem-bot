import logging
from dataclasses import dataclass
from typing import List, Tuple

logger = logging.getLogger(__name__)


from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Tuple
import logging

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
    Simple MLM commission calculator.
    """

    # проценты по уровням
    LEVEL_RATES = [
        Decimal("0.20"),  # 1 линия
        Decimal("0.10"),  # 2 линия
        Decimal("0.05"),  # 3 линия
        Decimal("0.05"),  # 4 линия
        Decimal("0.05"),  # 5 линия
    ]

    def calculate_purchase_commissions(
        self,
        purchase_amount: Decimal,
        buying_partner_id: int,
        upline_chain: List[Tuple[int, bool]]
    ) -> List[CommissionResult]:
        """
        Calculate MLM commissions for purchase.
        upline_chain = [(partner_id, is_active)]
        """

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

        logger.info(
            f"Calculated {len(commissions)} commissions for purchase by {buying_partner_id}"
        )

        return commissions