import asyncio

from core.commission import CommissionCalculator
from database.models import Commission, Partner, Purchase
from database.models_balance import Balance, BalanceTransaction
from database.models_stats import PartnerStats
from services import order_processor
from services.order_processor import OrderProcessor


def test_failed_commission_rolls_back_partner_purchase_and_commission(
    isolated_database,
    monkeypatch,
):
    session = isolated_database()
    roots = [
        Partner(first_name="Atomic Root 1", lineage=[]),
        Partner(first_name="Atomic Root 2", lineage=[]),
    ]
    session.add_all(roots)
    session.commit()
    root_id = roots[0].id
    session.close()

    class FailingCalculator:
        def __init__(self, db, bot):
            self.db = db

        async def process_purchase(self, purchase):
            self.db.add(
                Commission(
                    partner_id=root_id,
                    purchase_id=purchase.id,
                    source_partner_id=purchase.partner_id,
                    level=1,
                    rate=0.2,
                    base_amount=1000,
                    amount=200,
                )
            )
            self.db.flush()
            raise RuntimeError("Injected commission failure")

    monkeypatch.setattr(order_processor, "SessionLocal", isolated_database)
    monkeypatch.setattr(
        order_processor,
        "CommissionCalculator",
        FailingCalculator,
    )

    success = asyncio.run(
        OrderProcessor().process_order_data(
            {
                "id": 90001,
                "customer_id": 10,
                "total": "1000.00",
                "status": "completed",
                "billing": {
                    "email": "atomicity@example.test",
                    "first_name": "Atomic",
                    "last_name": "Buyer",
                    "phone": "+10000000010",
                },
            }
        )
    )

    assert success is False

    session = isolated_database()
    try:
        assert session.query(Partner).filter_by(
            email="atomicity@example.test"
        ).count() == 0
        assert session.query(Purchase).filter_by(
            ext_ref="90001"
        ).count() == 0
        assert session.query(Commission).count() == 0
        assert session.query(PartnerStats).count() == 0
    finally:
        session.close()


def test_failure_after_real_commission_credit_rolls_back_entire_order(
    isolated_database,
    monkeypatch,
):
    session = isolated_database()
    roots = [
        Partner(first_name="Credit Rollback Root 1", lineage=[]),
        Partner(first_name="Credit Rollback Root 2", lineage=[]),
    ]
    session.add_all(roots)
    session.commit()
    root_ids = [root.id for root in roots]
    session.close()

    class FailingAfterCreditCalculator:
        def __init__(self, db, bot):
            self.calculator = CommissionCalculator(db, bot)

        async def process_purchase(self, purchase):
            await self.calculator.process_purchase(purchase)
            raise RuntimeError("Injected failure after balance credit")

    monkeypatch.setattr(order_processor, "SessionLocal", isolated_database)
    monkeypatch.setattr(
        order_processor,
        "CommissionCalculator",
        FailingAfterCreditCalculator,
    )

    success = asyncio.run(
        OrderProcessor().process_order_data(
            {
                "id": 90003,
                "customer_id": 12,
                "total": "1000.00",
                "status": "completed",
                "billing": {
                    "email": "credit-rollback@example.test",
                    "first_name": "Credit",
                    "last_name": "Rollback",
                    "phone": "+10000000012",
                },
            }
        )
    )

    assert success is False

    session = isolated_database()
    try:
        assert session.query(Partner).filter_by(
            email="credit-rollback@example.test"
        ).count() == 0
        assert session.query(Purchase).filter_by(ext_ref="90003").count() == 0
        assert session.query(Commission).count() == 0
        assert session.query(Balance).filter(
            Balance.partner_id.in_(root_ids)
        ).count() == 0
        assert session.query(BalanceTransaction).count() == 0
        assert session.query(PartnerStats).count() == 0
    finally:
        session.close()


def test_duplicate_woocommerce_order_is_ignored(
    isolated_database,
    monkeypatch,
):
    session = isolated_database()
    roots = [
        Partner(first_name="Duplicate Root 1", lineage=[]),
        Partner(first_name="Duplicate Root 2", lineage=[]),
    ]
    session.add_all(roots)
    session.commit()
    session.close()

    monkeypatch.setattr(order_processor, "SessionLocal", isolated_database)
    calculator_calls = []

    class SuccessfulCalculator:
        def __init__(self, db, bot):
            pass

        async def process_purchase(self, purchase):
            calculator_calls.append(purchase.id)
            purchase.is_commission_processed = True

    monkeypatch.setattr(
        order_processor,
        "CommissionCalculator",
        SuccessfulCalculator,
    )
    payload = {
        "id": 90002,
        "customer_id": 11,
        "total": "1000.00",
        "status": "completed",
        "billing": {
            "email": "duplicate@example.test",
            "first_name": "Duplicate",
            "last_name": "Buyer",
            "phone": "+10000000011",
        },
    }
    processor = OrderProcessor()

    assert asyncio.run(processor.process_order_data(payload)) is True
    assert asyncio.run(processor.process_order_data(payload)) is True
    assert len(calculator_calls) == 1

    session = isolated_database()
    try:
        purchase = session.query(Purchase).filter_by(
            ext_ref="90002"
        ).one()
        assert session.query(Purchase).filter_by(ext_ref="90002").count() == 1
        buyer = session.query(Partner).filter_by(
            email="duplicate@example.test"
        ).one()
        buyer_stats = session.get(PartnerStats, buyer.id)
        assert buyer_stats.personal_turnover == 1000
        assert buyer.rank == "Partner"
        root_stats = session.get(PartnerStats, buyer.upline_id)
        assert root_stats.network_turnover == 1000
        assert purchase.is_commission_processed is True
    finally:
        session.close()
