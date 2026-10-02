from decimal import Decimal

from sqlalchemy.orm import Session

from database.models import Commission, CommissionStatus
from database.models_balance import BalanceTransactionType
from core.balance_service import BalanceService


class CommissionService:
    def __init__(self, session: Session):
        self.session = session
        self.balance_service = BalanceService(session)

    def approve_commission(self, commission: Commission) -> bool:
        if commission.status != CommissionStatus.PENDING:
            return False

        self.balance_service.add_funds(
            partner_id=commission.partner_id,
            amount=Decimal(str(commission.amount)),
            tx_type=BalanceTransactionType.COMMISSION,
            reference_id=commission.id,
        )

        commission.status = CommissionStatus.APPROVED

        return True