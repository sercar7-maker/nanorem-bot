from decimal import Decimal

from database.db import SessionLocal
from database.models import Partner
from database.models_balance import BalanceTransactionType
from core.balance_service import BalanceService


def test_balance_hold_release_and_confirm():
    session = SessionLocal()

    try:
        partner = Partner(
            first_name="Balance Test",
            username="balance_test",
        )

        session.add(partner)
        session.flush()

        service = BalanceService(session)

        # Получаем существующий баланс партнёра.
        # Если его нет, BalanceService создаст его сам.
        balance = service._get_balance(partner.id)

        # Для теста начинаем с нулевого состояния.
        balance.amount = Decimal("0.00")
        balance.hold = Decimal("0.00")
        session.flush()

        # Начальное начисление 1000.
        service.add_funds(
            partner_id=partner.id,
            amount=Decimal("1000.00"),
            tx_type=BalanceTransactionType.COMMISSION,
            reference_id=900001,
        )

        assert balance.amount == Decimal("1000.00")
        assert balance.hold == Decimal("0.00")

        # Блокируем 300 под вывод.
        service.hold_funds(
            partner_id=partner.id,
            amount=Decimal("300.00"),
            reference_id=900002,
        )

        assert balance.amount == Decimal("700.00")
        assert balance.hold == Decimal("300.00")

        # Отменяем вывод.
        service.release_hold(
            partner_id=partner.id,
            amount=Decimal("300.00"),
            reference_id=900002,
        )

        assert balance.amount == Decimal("1000.00")
        assert balance.hold == Decimal("0.00")

        # Снова блокируем 300.
        service.hold_funds(
            partner_id=partner.id,
            amount=Decimal("300.00"),
            reference_id=900003,
        )

        assert balance.amount == Decimal("700.00")
        assert balance.hold == Decimal("300.00")

        # Подтверждаем успешную выплату.
        service.confirm_hold_spent(
            partner_id=partner.id,
            amount=Decimal("300.00"),
            reference_id=900003,
        )

        assert balance.amount == Decimal("700.00")
        assert balance.hold == Decimal("0.00")

    finally:
        session.rollback()
        session.close()