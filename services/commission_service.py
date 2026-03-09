from sqlalchemy.orm import Session

from database.models import Commission, CommissionStatus
from services.balance_service import BalanceService


class CommissionService:

    def __init__(self, session: Session):
        self.session = session
        self.balance_service = BalanceService(session)

    def approve_commission(self, commission: Commission):

        if commission.status != CommissionStatus.PENDING:
            return False

        commission.status = CommissionStatus.APPROVED

        self.balance_service.add_commission(
            partner_id=commission.partner_id,
            amount=commission.amount,
            source=f"commission:{commission.id}"
        )

        self.session.commit()

        return True