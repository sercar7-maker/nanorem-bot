import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import event

from config import configured_activity_thresholds, load_activity_thresholds
from database.models import OrderStatus, Partner, PartnerStatus, Purchase
from services import order_processor, subscription_service
from services.order_processor import OrderProcessor
from services.partner_service import PartnerService
from services.subscription_service import SubscriptionService


@pytest.fixture(autouse=True)
def pin_default_activity_thresholds(monkeypatch):
    """Keep activity tests on the owner's defaults despite local env."""
    monkeypatch.setattr(
        subscription_service,
        "MONTHLY_PURCHASE_AMOUNT",
        Decimal("3000.00"),
    )
    monkeypatch.setattr(
        subscription_service,
        "ANNUAL_PURCHASE_AMOUNT",
        Decimal("10000.00"),
    )


def _create_root_pair() -> tuple[int, int]:
    service = PartnerService()
    first = service.create_root(first_name="Subscription test Root 1")
    second = service.create_root(first_name="Subscription test Root 2")
    return first.id, second.id


def _purchase(
    session,
    partner_id: int,
    amount: str,
    paid_at: datetime,
    order_id: str,
) -> Purchase:
    purchase = Purchase(
        purchase_number=f"SUB-{order_id}",
        ext_ref=order_id,
        partner_id=partner_id,
        amount=Decimal(amount),
        status=OrderStatus.PAID,
        paid_at=paid_at,
        created_at=paid_at,
    )
    session.add(purchase)
    session.flush()
    return purchase


def test_3000_rubles_grants_one_calendar_month(isolated_database):
    session = isolated_database()
    partner = Partner(first_name="Monthly subscription")
    session.add(partner)
    session.flush()
    purchase = _purchase(
        session,
        partner.id,
        "3000.00",
        datetime(2026, 10, 7, 12),
        "monthly-single",
    )

    end = SubscriptionService(session).apply_purchase(purchase)

    assert end == datetime(2026, 11, 7, 12)
    assert partner.status == PartnerStatus.ACTIVE
    session.close()


def test_repeated_3000_ruble_purchases_extend_existing_term(isolated_database):
    session = isolated_database()
    partner = Partner(first_name="Repeated monthly subscription")
    session.add(partner)
    session.flush()
    purchase = _purchase(
        session,
        partner.id,
        "3000.00",
        datetime(2026, 10, 7, 12),
        "monthly-first",
    )
    first_result = SubscriptionService(session).apply_purchase(purchase)
    second_purchase = _purchase(
        session,
        partner.id,
        "3000.00",
        datetime(2026, 10, 14, 12),
        "monthly-second",
    )

    second_result = SubscriptionService(session).apply_purchase(second_purchase)

    assert first_result == datetime(2026, 11, 7, 12)
    assert second_result == datetime(2026, 12, 7, 12)
    session.close()


def test_10000_rubles_grants_one_year(isolated_database):
    session = isolated_database()
    partner = Partner(first_name="Annual subscription")
    session.add(partner)
    session.flush()
    purchase = _purchase(
        session,
        partner.id,
        "10000.00",
        datetime(2026, 10, 7, 12),
        "annual-single",
    )

    end = SubscriptionService(session).apply_purchase(purchase)

    assert end == datetime(2027, 10, 7, 12)
    assert partner.annual_activity_until == end
    session.close()


@pytest.mark.parametrize("next_amount", ["3000.00", "10000.00"])
def test_purchases_during_annual_activity_do_not_extend_it(
    isolated_database,
    next_amount,
):
    session = isolated_database()
    partner = Partner(first_name="Annual activity does not stack")
    session.add(partner)
    session.flush()
    first_purchase = _purchase(
        session,
        partner.id,
        "10000.00",
        datetime(2026, 10, 7, 12),
        f"annual-does-not-stack-{next_amount}",
    )
    service = SubscriptionService(session)
    annual_end = service.apply_purchase(first_purchase)
    next_purchase = _purchase(
        session,
        partner.id,
        next_amount,
        datetime(2026, 11, 7, 12),
        f"annual-follow-up-{next_amount}",
    )

    assert service.apply_purchase(next_purchase) == annual_end
    assert partner.subscription_end_date == annual_end
    assert partner.annual_activity_until == annual_end
    session.close()


def test_purchase_after_annual_activity_expiry_opens_new_year(
    isolated_database,
):
    session = isolated_database()
    old_annual_end = datetime(2026, 10, 7, 12)
    partner = Partner(
        first_name="Annual activity renewed after expiry",
        subscription_end_date=old_annual_end,
        annual_activity_until=old_annual_end,
    )
    session.add(partner)
    session.flush()
    purchase = _purchase(
        session,
        partner.id,
        "10000.00",
        datetime(2026, 10, 8, 12),
        "annual-after-expiry",
    )

    end = SubscriptionService(session).apply_purchase(purchase)

    assert end == datetime(2027, 10, 8, 12)
    assert partner.annual_activity_until == end
    session.close()


def test_root_partner_does_not_receive_subscription_activity(
    isolated_database,
):
    session = isolated_database()
    root = Partner(
        first_name="Root excluded from subscription service",
    )
    session.add(root)
    session.flush()
    root.root_id = root.id
    purchase = _purchase(
        session,
        root.id,
        "10000.00",
        datetime(2026, 10, 7, 12),
        "root-no-subscription",
    )

    assert SubscriptionService(session).apply_purchase(purchase) is None
    assert root.subscription_end_date is None
    assert root.annual_activity_until is None
    session.close()


def test_root_allocation_lock_is_acquired_before_month_purchase_query(
    isolated_database,
):
    session = isolated_database()
    partner = Partner(first_name="Subscription lock order")
    session.add(partner)
    session.flush()
    purchase = _purchase(
        session,
        partner.id,
        "3000.00",
        datetime(2026, 10, 7, 12),
        "subscription-lock-order",
    )
    statements = []
    connection = session.connection()

    def record_statement(
        conn,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ):
        statements.append(statement.lower())

    event.listen(connection, "before_cursor_execute", record_statement)
    try:
        SubscriptionService(session).apply_purchase(purchase)
    finally:
        event.remove(connection, "before_cursor_execute", record_statement)

    lock_index = next(
        index
        for index, statement in enumerate(statements)
        if "update root_allocation_lock" in statement
    )
    month_read_index = next(
        index
        for index, statement in enumerate(statements)
        if "from purchases" in statement
    )
    assert lock_index < month_read_index
    session.close()


def test_calendar_month_aggregate_replaces_months_with_one_year(
    isolated_database,
):
    session = isolated_database()
    partner = Partner(first_name="Aggregated annual subscription")
    session.add(partner)
    session.flush()
    first_purchase = _purchase(
        session,
        partner.id,
        "3000.00",
        datetime(2026, 10, 7, 12),
        "aggregate-1",
    )
    second_purchase = _purchase(
        session,
        partner.id,
        "3000.00",
        datetime(2026, 10, 14, 12),
        "aggregate-2",
    )
    threshold_purchase = _purchase(
        session,
        partner.id,
        "4000.00",
        datetime(2026, 10, 21, 12),
        "aggregate-threshold",
    )

    SubscriptionService(session).apply_purchase(first_purchase)
    SubscriptionService(session).apply_purchase(second_purchase)
    end = SubscriptionService(session).apply_purchase(threshold_purchase)

    assert end == datetime(2027, 10, 21, 12)
    session.close()


def test_aggregate_threshold_does_not_cross_calendar_months(isolated_database):
    session = isolated_database()
    partner = Partner(first_name="Calendar window subscription")
    session.add(partner)
    session.flush()
    october_purchase = _purchase(
        session,
        partner.id,
        "3000.00",
        datetime(2026, 10, 31, 12),
        "october-month",
    )
    november_purchase = _purchase(
        session,
        partner.id,
        "3000.00",
        datetime(2026, 11, 1, 12),
        "november-month",
    )

    SubscriptionService(session).apply_purchase(october_purchase)
    end = SubscriptionService(session).apply_purchase(november_purchase)

    assert end == datetime(2026, 12, 31, 12)
    session.close()


def test_purchase_after_expiry_starts_new_subscription_at_purchase_date(
    isolated_database,
):
    session = isolated_database()
    old_expiry = datetime(2026, 9, 7, 12)
    partner = Partner(
        first_name="Expired subscription",
        status=PartnerStatus.INACTIVE,
        subscription_end_date=old_expiry,
    )
    session.add(partner)
    session.flush()
    purchase = _purchase(
        session,
        partner.id,
        "3000.00",
        datetime(2026, 10, 7, 12),
        "after-expiry",
    )

    end = SubscriptionService(session).apply_purchase(purchase)

    assert end == datetime(2026, 11, 7, 12)
    assert partner.status == PartnerStatus.ACTIVE
    session.close()


def test_purchase_during_activity_extends_from_existing_expiry(isolated_database):
    session = isolated_database()
    partner = Partner(
        first_name="Active subscription",
        status=PartnerStatus.ACTIVE,
        subscription_end_date=datetime(2026, 11, 7, 12),
    )
    session.add(partner)
    session.flush()
    purchase = _purchase(
        session,
        partner.id,
        "3000.00",
        datetime(2026, 10, 14, 12),
        "during-activity",
    )

    end = SubscriptionService(session).apply_purchase(purchase)

    assert end == datetime(2026, 12, 7, 12)
    session.close()


def test_later_existing_expiry_is_never_reduced(isolated_database):
    session = isolated_database()
    later_expiry = datetime(2030, 1, 31, 12)
    partner = Partner(
        first_name="Manual extended subscription",
        subscription_end_date=later_expiry,
    )
    session.add(partner)
    session.flush()
    purchase = _purchase(
        session,
        partner.id,
        "10000.00",
        datetime(2026, 10, 7, 12),
        "keep-later-expiry",
    )

    end = SubscriptionService(session).apply_purchase(purchase)

    assert end == later_expiry
    session.close()


@pytest.mark.parametrize(
    ("start", "expected"),
    [
        (datetime(2025, 1, 31, 12), datetime(2025, 2, 28, 12)),
        (datetime(2024, 1, 31, 12), datetime(2024, 2, 29, 12)),
    ],
)
def test_calendar_month_end_is_clamped_correctly(
    isolated_database,
    start,
    expected,
):
    session = isolated_database()
    partner = Partner(first_name="Month end subscription")
    session.add(partner)
    session.flush()
    first_purchase = _purchase(
        session,
        partner.id,
        "3000.00",
        start,
        f"month-end-{start.year}",
    )

    assert SubscriptionService(session).apply_purchase(first_purchase) == expected
    session.close()


def test_end_of_month_anchor_is_preserved_across_extensions(isolated_database):
    session = isolated_database()
    partner = Partner(first_name="End of month renewal")
    session.add(partner)
    session.flush()
    first_purchase = _purchase(
        session,
        partner.id,
        "3000.00",
        datetime(2025, 1, 31, 12),
        "eom-january",
    )
    second_purchase = _purchase(
        session,
        partner.id,
        "3000.00",
        datetime(2025, 2, 20, 12),
        "eom-february",
    )

    SubscriptionService(session).apply_purchase(first_purchase)
    assert SubscriptionService(session).apply_purchase(second_purchase) == (
        datetime(2025, 3, 31, 12)
    )
    session.close()


def test_partner_active_state_requires_unexpired_subscription(isolated_database):
    session = isolated_database()
    active = Partner(
        first_name="Active until tomorrow",
        status=PartnerStatus.ACTIVE,
        subscription_end_date=datetime.now(timezone.utc)
        .replace(tzinfo=None)
        + timedelta(days=1),
    )
    expired = Partner(
        first_name="Already expired",
        status=PartnerStatus.ACTIVE,
        subscription_end_date=datetime.now(timezone.utc)
        .replace(tzinfo=None)
        - timedelta(seconds=1),
    )
    no_subscription = Partner(
        first_name="No subscription",
        status=PartnerStatus.ACTIVE,
    )
    session.add_all([active, expired, no_subscription])
    session.flush()

    assert active.is_active is True
    assert expired.is_active is False
    assert no_subscription.is_active is False
    session.close()


def test_aware_purchase_timestamp_is_normalized_to_utc(isolated_database):
    normalized = OrderProcessor._purchase_paid_at(
        {"date_paid": "2026-10-07T15:00:00+03:00"}
    )

    assert normalized == datetime(2026, 10, 7, 12)


def test_duplicate_webhook_does_not_extend_subscription_twice(
    isolated_database,
    monkeypatch,
):
    root_ids = _create_root_pair()
    session = isolated_database()
    buyer = Partner(
        first_name="Webhook subscriber",
        email="webhook-subscriber@example.test",
        upline_id=root_ids[0],
        root_id=root_ids[0],
        lineage=[root_ids[0]],
    )
    session.add(buyer)
    session.commit()
    session.close()

    monkeypatch.setattr(order_processor, "SessionLocal", isolated_database)
    payload = {
        "id": "subscription-webhook-1",
        "customer_id": 51,
        "total": "3000.00",
        "status": "completed",
        "date_paid_gmt": "2026-10-07T12:00:00",
        "billing": {
            "email": "webhook-subscriber@example.test",
            "first_name": "Webhook",
        },
    }
    processor = OrderProcessor()

    assert asyncio.run(processor.process_order_data(payload)) is True
    session = isolated_database()
    partner_id = session.query(Partner).filter_by(
        email="webhook-subscriber@example.test"
    ).one().id
    first_end = session.get(Partner, partner_id).subscription_end_date
    session.close()

    assert asyncio.run(processor.process_order_data(payload)) is True

    session = isolated_database()
    assert session.query(Purchase).filter_by(
        ext_ref="subscription-webhook-1"
    ).count() == 1
    assert session.get(Partner, partner_id).subscription_end_date == first_end
    session.close()


def test_duplicate_annual_webhook_does_not_extend_year_twice(
    isolated_database,
    monkeypatch,
):
    root_ids = _create_root_pair()
    session = isolated_database()
    buyer = Partner(
        first_name="Annual webhook subscriber",
        email="annual-webhook-subscriber@example.test",
        upline_id=root_ids[0],
        root_id=root_ids[0],
        lineage=[root_ids[0]],
    )
    session.add(buyer)
    session.commit()
    session.close()

    monkeypatch.setattr(order_processor, "SessionLocal", isolated_database)
    payload = {
        "id": "annual-subscription-webhook-1",
        "customer_id": 53,
        "total": "10000.00",
        "status": "completed",
        "date_paid_gmt": "2026-10-07T12:00:00",
        "billing": {
            "email": "annual-webhook-subscriber@example.test",
            "first_name": "Annual",
        },
    }
    processor = OrderProcessor()

    assert asyncio.run(processor.process_order_data(payload)) is True
    session = isolated_database()
    partner = session.query(Partner).filter_by(
        email="annual-webhook-subscriber@example.test"
    ).one()
    first_end = partner.subscription_end_date
    first_annual_end = partner.annual_activity_until
    partner_id = partner.id
    session.close()

    assert asyncio.run(processor.process_order_data(payload)) is True

    session = isolated_database()
    assert session.query(Purchase).filter_by(
        ext_ref="annual-subscription-webhook-1"
    ).count() == 1
    partner = session.get(Partner, partner_id)
    assert partner.subscription_end_date == first_end
    assert partner.annual_activity_until == first_annual_end == first_end
    session.close()


def test_commission_failure_rolls_back_subscription_and_purchase(
    isolated_database,
    monkeypatch,
):
    root_ids = _create_root_pair()
    session = isolated_database()
    buyer = Partner(
        first_name="Rollback subscriber",
        email="rollback-subscriber@example.test",
        upline_id=root_ids[0],
        root_id=root_ids[0],
        lineage=[root_ids[0]],
    )
    session.add(buyer)
    session.commit()
    buyer_id = buyer.id
    session.close()

    class FailingCalculator:
        def __init__(self, db, bot):
            pass

        async def process_purchase(self, purchase):
            raise RuntimeError("injected commission failure")

    monkeypatch.setattr(order_processor, "SessionLocal", isolated_database)
    monkeypatch.setattr(
        order_processor,
        "CommissionCalculator",
        FailingCalculator,
    )
    success = asyncio.run(
        OrderProcessor().process_order_data(
            {
                "id": "subscription-rollback",
                "customer_id": 52,
                "total": "3000.00",
                "status": "completed",
                "date_paid_gmt": "2026-10-07T12:00:00",
                "billing": {
                    "email": "rollback-subscriber@example.test",
                    "first_name": "Rollback",
                },
            }
        )
    )

    session = isolated_database()
    partner = session.get(Partner, buyer_id)
    assert success is False
    assert partner.subscription_end_date is None
    assert session.query(Purchase).filter_by(
        ext_ref="subscription-rollback"
    ).count() == 0
    session.close()


def test_purchase_below_monthly_threshold_does_not_grant_activity(
    isolated_database,
):
    session = isolated_database()
    partner = Partner(first_name="Below monthly threshold")
    session.add(partner)
    session.flush()
    purchase = _purchase(
        session,
        partner.id,
        "2999.99",
        datetime(2026, 10, 7, 12),
        "below-monthly",
    )

    assert SubscriptionService(session).apply_purchase(purchase) is None
    assert partner.subscription_end_date is None
    assert partner.annual_activity_until is None
    session.close()


def test_purchase_above_monthly_threshold_grants_one_month(
    isolated_database,
):
    session = isolated_database()
    partner = Partner(first_name="Above monthly threshold")
    session.add(partner)
    session.flush()
    purchase = _purchase(
        session,
        partner.id,
        "3500.00",
        datetime(2026, 10, 7, 12),
        "above-monthly",
    )

    end = SubscriptionService(session).apply_purchase(purchase)

    assert end == datetime(2026, 11, 7, 12)
    assert partner.annual_activity_until is None
    session.close()


def test_several_purchases_in_one_month_reach_annual_threshold(
    isolated_database,
):
    session = isolated_database()
    partner = Partner(first_name="Several purchases reach annual")
    session.add(partner)
    session.flush()
    service = SubscriptionService(session)
    first = _purchase(
        session,
        partner.id,
        "2000.00",
        datetime(2026, 10, 7, 12),
        "annual-parts-1",
    )
    assert service.apply_purchase(first) is None
    second = _purchase(
        session,
        partner.id,
        "3000.00",
        datetime(2026, 10, 14, 12),
        "annual-parts-2",
    )
    assert service.apply_purchase(second) == datetime(2026, 11, 14, 12)
    third = _purchase(
        session,
        partner.id,
        "5000.00",
        datetime(2026, 10, 21, 12),
        "annual-parts-3",
    )
    end = service.apply_purchase(third)

    assert end == datetime(2027, 10, 21, 12)
    assert partner.annual_activity_until == end
    session.close()


def test_purchases_above_monthly_do_not_sum_across_calendar_months(
    isolated_database,
):
    session = isolated_database()
    partner = Partner(first_name="No cross-month annual sum")
    session.add(partner)
    session.flush()
    october = _purchase(
        session,
        partner.id,
        "6000.00",
        datetime(2026, 10, 7, 12),
        "cross-october",
    )
    november = _purchase(
        session,
        partner.id,
        "6000.00",
        datetime(2026, 11, 8, 12),
        "cross-november",
    )
    service = SubscriptionService(session)

    assert service.apply_purchase(october) == datetime(2026, 11, 7, 12)
    end = service.apply_purchase(november)

    assert end == datetime(2026, 12, 8, 12)
    assert partner.annual_activity_until is None
    session.close()


def test_alternative_thresholds_replace_owner_defaults(
    isolated_database,
    monkeypatch,
):
    monkeypatch.setattr(
        subscription_service,
        "MONTHLY_PURCHASE_AMOUNT",
        Decimal("2000.00"),
    )
    monkeypatch.setattr(
        subscription_service,
        "ANNUAL_PURCHASE_AMOUNT",
        Decimal("4500.00"),
    )
    session = isolated_database()
    partner = Partner(first_name="Alternative thresholds")
    session.add(partner)
    session.flush()
    service = SubscriptionService(session)
    below = _purchase(
        session,
        partner.id,
        "1999.99",
        datetime(2026, 10, 7, 12),
        "alt-below",
    )
    assert service.apply_purchase(below) is None
    monthly = _purchase(
        session,
        partner.id,
        "2000.00",
        datetime(2026, 10, 8, 12),
        "alt-monthly",
    )
    assert service.apply_purchase(monthly) == datetime(2026, 11, 8, 12)
    annual = _purchase(
        session,
        partner.id,
        "4500.00",
        datetime(2026, 10, 9, 12),
        "alt-annual",
    )
    end = service.apply_purchase(annual)

    assert end == datetime(2027, 10, 9, 12)
    assert partner.annual_activity_until == end
    session.close()


def test_activity_thresholds_use_defaults_when_unset(monkeypatch):
    monkeypatch.delenv("MONTHLY_PURCHASE_AMOUNT", raising=False)
    monkeypatch.delenv("ANNUAL_PURCHASE_AMOUNT", raising=False)

    monthly, annual = configured_activity_thresholds()

    assert monthly == Decimal("3000.00")
    assert annual == Decimal("10000.00")


@pytest.mark.parametrize(
    ("monthly_raw", "annual_raw"),
    [
        ("0", "10000.00"),
        ("-1.00", "10000.00"),
        ("NaN", "10000.00"),
        ("Infinity", "10000.00"),
        ("3000.001", "10000.00"),
        ("3000.00", "3000.00"),
        ("10000.00", "3000.00"),
        ("not-a-number", "10000.00"),
    ],
)
def test_invalid_activity_thresholds_raise(monthly_raw, annual_raw):
    with pytest.raises(RuntimeError):
        load_activity_thresholds(monthly_raw, annual_raw)
