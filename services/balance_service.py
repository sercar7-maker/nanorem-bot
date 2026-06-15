from sqlalchemy.orm import Session
from sqlalchemy import select
from decimal import Decimal

from database.models_balance import Balance, BalanceTransaction, BalanceTransactionType


class BalanceService:

    def __init__(self, session: Session):
        self.session = session

    def get_or_create_balance(self, partner_id: int):

        balance = self.session.execute(
            select(Balance).where(Balance.partner_id == partner_id)
        ).scalar_one_or_none()

        if balance is None:

            balance = Balance(
                partner_id=partner_id,
                amount=Decimal("0"),
                hold=Decimal("0")
            )

            self.session.add(balance)
            self.session.commit()

        return balance

    def add_commission(self, partner_id: int, amount: float, source: str):

        balance = self.get_or_create_balance(partner_id)

        commission_amount = Decimal(str(amount))

        balance.amount += commission_amount

        transaction = BalanceTransaction(
            partner_id=partner_id,
            amount=commission_amount,
            type=BalanceTransactionType.COMMISSION,
            description=source
        )

        self.session.add(transaction)
        self.session.commit()

        return balance.amount