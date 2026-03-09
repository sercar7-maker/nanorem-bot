import logging
from dataclasses import dataclass
from typing import List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CommissionResult:
    partner_id: int
    level: int
    rate: float
    base_amount: float
    amount: float
    compressed: bool = False
    notes: str = ""


class CommissionCalculator:
    """
    Simple MLM commission calculator.
    """

    # проценты по уровням
    LEVEL_RATES = [0.10, 0.05, 0.03, 0.02, 0.01]

    def calculate_purchase_commissions(
        self,
        purchase_amount: float,
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
                        amount=0,
                        compressed=True,
                        notes="Partner inactive"
                    )
                )
                continue

            amount = purchase_amount * rate

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