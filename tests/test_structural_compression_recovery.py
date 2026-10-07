import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from core.commission import CommissionCalculator
from database.models import (
    Commission,
    CommissionStatus,
    OrderStatus,
    Partner,
    PartnerRecoveryEvent,
    PartnerStatus,
    Purchase,
)
from database.models_balance import (
    Balance,
    BalanceTransaction,
    BalanceTransactionType,
)
from services.order_processor import OrderProcessor
from services.order_processor import RootPairNotReadyError
from services.structural_compression_service import (
    RecoveryConflictError,
    StructuralCompressionService,
    _add_calendar_months,
)
from database.migrations import upgrade_schema
import scheduler


def _tree(session, *, root_index=2, name_prefix="Recovery"):
    roots = []
    for index in (1, 2):
        root = Partner(
            first_name=f"{name_prefix} root {index}",
            lineage=[],
            subscription_end_date=datetime.now(timezone.utc)
            .replace(tzinfo=None)
            + timedelta(days=365),
        )
        session.add(root)
        session.flush()
        root.root_id = root.id
        roots.append(root)

    root = roots[root_index - 1]
    parent = Partner(
        first_name=f"{name_prefix} parent",
        upline_id=root.id,
        root_id=root.id,
        lineage=[root.id],
        subscription_end_date=datetime.now(timezone.utc)
        .replace(tzinfo=None)
        + timedelta(days=365),
    )
    session.add(parent)
    session.flush()

    expired_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        days=1
    )
    returning = Partner(
        first_name=f"{name_prefix} returning",
        email=f"{name_prefix.lower()}-returning@example.test",
        status=PartnerStatus.ACTIVE,
        subscription_end_date=expired_at,
        upline_id=parent.id,
        root_id=root.id,
        lineage=[parent.id, root.id],
    )
    session.add(returning)
    session.flush()

    children = []
    for name in ("child c", "child d"):
        child = Partner(
            first_name=f"{name_prefix} {name}",
            upline_id=returning.id,
            root_id=root.id,
            lineage=[returning.id, parent.id, root.id],
            subscription_end_date=datetime.now(timezone.utc)
            .replace(tzinfo=None)
            + timedelta(days=365),
        )
        session.add(child)
        session.flush()
        grandchild = Partner(
            first_name=f"{name_prefix} {name} grandchild",
            upline_id=child.id,
            root_id=root.id,
            lineage=[child.id, returning.id, parent.id, root.id],
            subscription_end_date=datetime.now(timezone.utc)
            .replace(tzinfo=None)
            + timedelta(days=365),
        )
        session.add(grandchild)
        children.append((child, grandchild))

    session.flush()
    return roots, parent, returning, children, expired_at


def _recover(session, partner, when):
    partner.status = PartnerStatus.ACTIVE
    partner.subscription_end_date = when + timedelta(days=30)
    purchase = Purchase(
        purchase_number=f"RECOVERY-{partner.id}-{when.isoformat()}",
        partner_id=partner.id,
        amount=Decimal("3000.00"),
        status=OrderStatus.PAID,
        paid_at=when,
    )
    session.add(purchase)
    session.flush()
    StructuralCompressionService(session).process_paid_purchase(
        partner,
        purchase,
    )
    return purchase


def test_expiration_compresses_immediately_and_saves_recovery_snapshot(
    isolated_database,
):
    session = isolated_database()
    roots, parent, returning, children, expired_at = _tree(session)
    now = expired_at + timedelta(seconds=1)

    compressed = StructuralCompressionService(
        session
    ).expire_due_partners(now)

    event = session.query(PartnerRecoveryEvent).filter_by(
        partner_id=returning.id
    ).one()
    assert compressed == 1
    assert returning.status == PartnerStatus.INACTIVE
    assert returning.upline_id is None
    assert returning.lineage == []
    assert event.old_upline_id == parent.id
    assert event.root_id == roots[1].id
    assert event.recovery_until == _add_calendar_months(expired_at, 3)
    assert StructuralCompressionService(session).expire_due_partners(now) == 0
    assert session.query(PartnerRecoveryEvent).filter_by(
        partner_id=returning.id
    ).count() == 1
    for child, grandchild in children:
        assert child.upline_id == parent.id
        assert child.lineage == [parent.id, roots[1].id]
        assert grandchild.upline_id == child.id
        assert grandchild.lineage == [
            child.id,
            parent.id,
            roots[1].id,
        ]
    session.close()


def test_not_yet_expired_partner_keeps_current_position(isolated_database):
    session = isolated_database()
    _, parent, returning, children, expired_at = _tree(session)

    assert StructuralCompressionService(session).expire_due_partners(
        expired_at - timedelta(seconds=1)
    ) == 0
    assert returning.upline_id == parent.id
    assert all(child.upline_id == returning.id for child, _ in children)
    session.close()


def test_permanent_root_is_not_expired_or_compressed(isolated_database):
    session = isolated_database()
    expired_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        days=1
    )
    root = Partner(
        first_name="Permanent Root",
        status=PartnerStatus.ACTIVE,
        subscription_end_date=expired_at,
        lineage=[],
    )
    session.add(root)
    session.flush()
    root.root_id = root.id
    service = StructuralCompressionService(session)

    assert service.expire_due_partners(expired_at + timedelta(seconds=1)) == 0
    assert service.compress_partner(
        root,
        lost_activity_at=expired_at,
    ) is False
    assert root.status == PartnerStatus.ACTIVE
    assert root.upline_id is None
    assert root.root_id == root.id
    assert session.query(PartnerRecoveryEvent).filter_by(
        partner_id=root.id
    ).count() == 0
    session.close()


def test_woocommerce_does_not_create_partner_before_root_pair_exists(
    isolated_database,
    monkeypatch,
):
    monkeypatch.setattr(
        "services.order_processor.SessionLocal",
        isolated_database,
    )
    order_data = {
        "id": 87001,
        "customer_id": 99001,
        "status": "completed",
        "total": "3000.00",
        "date_paid_gmt": "2026-10-07T12:00:00",
        "billing": {
            "email": "woocommerce-before-roots@example.test",
            "first_name": "Woo",
            "last_name": "Customer",
            "phone": "",
        },
    }

    with pytest.raises(
        RootPairNotReadyError,
        match="System is not ready for registration",
    ):
        asyncio.run(
            OrderProcessor().process_order_data(order_data)
        )

    session = isolated_database()
    try:
        assert session.query(Partner).count() == 0
        assert session.query(Purchase).count() == 0
    finally:
        session.close()


def test_woocommerce_root_purchase_is_recorded_without_activity_or_self_commission(
    isolated_database,
    monkeypatch,
):
    session = isolated_database()
    roots, _, _, _, _ = _tree(session, name_prefix="RootOrder")
    root = roots[0]
    root.email = "permanent-root-order@example.test"
    original_expiry = root.subscription_end_date
    original_annual_activity_until = (
        datetime.now(timezone.utc).replace(tzinfo=None)
        + timedelta(days=180)
    )
    root.annual_activity_until = original_annual_activity_until
    original_status = root.status
    root_id = root.id
    session.commit()
    session.close()
    monkeypatch.setattr(
        "services.order_processor.SessionLocal",
        isolated_database,
    )
    order_data = {
        "id": 87002,
        "customer_id": 99002,
        "status": "completed",
        "total": "3000.00",
        "date_paid_gmt": "2026-10-07T12:00:00",
        "billing": {
            "email": "permanent-root-order@example.test",
            "first_name": "Root",
            "last_name": "Founder",
            "phone": "",
        },
    }

    assert asyncio.run(
        OrderProcessor().process_order_data(order_data)
    ) is True

    session = isolated_database()
    try:
        root = session.get(Partner, root_id)
        purchase = session.query(Purchase).filter_by(
            ext_ref="87002"
        ).one()
        assert purchase.partner_id == root_id
        assert purchase.amount == Decimal("3000.00")
        assert purchase.status == OrderStatus.PAID
        assert purchase.is_commission_processed is True
        assert root.root_id == root.id
        assert root.status == original_status
        assert root.subscription_end_date == original_expiry
        assert root.annual_activity_until == original_annual_activity_until
        assert session.query(Commission).filter_by(
            purchase_id=purchase.id,
            partner_id=root_id,
        ).count() == 0
    finally:
        session.close()


def test_recovery_within_three_calendar_months_restores_parent_and_children(
    isolated_database,
):
    session = isolated_database()
    roots, parent, returning, children, expired_at = _tree(session)
    service = StructuralCompressionService(session)
    service.expire_due_partners(expired_at + timedelta(seconds=1))

    recovery_time = _add_calendar_months(expired_at, 3) - timedelta(seconds=1)
    _recover(session, returning, recovery_time)

    event = session.query(PartnerRecoveryEvent).filter_by(
        partner_id=returning.id
    ).one()
    assert event.status == "RESTORED"
    assert returning.upline_id == parent.id
    assert returning.root_id == roots[1].id
    assert returning.lineage == [parent.id, roots[1].id]
    for child, grandchild in children:
        assert child.upline_id == returning.id
        assert child.lineage == [returning.id, parent.id, roots[1].id]
        assert grandchild.upline_id == child.id
        assert grandchild.lineage == [
            child.id,
            returning.id,
            parent.id,
            roots[1].id,
        ]
    session.close()


def test_recovery_is_allowed_on_exact_three_month_deadline(isolated_database):
    session = isolated_database()
    _, parent, returning, _, expired_at = _tree(session)
    StructuralCompressionService(session).expire_due_partners(
        expired_at + timedelta(seconds=1)
    )

    deadline = _add_calendar_months(expired_at, 3)
    _recover(session, returning, deadline)

    assert returning.upline_id == parent.id
    assert session.query(PartnerRecoveryEvent).filter_by(
        partner_id=returning.id
    ).one().status == "RESTORED"
    session.close()


@pytest.mark.parametrize("root_index", [1, 2])
def test_late_reactivation_starts_directly_under_original_root(
    isolated_database,
    root_index,
):
    session = isolated_database()
    roots, parent, returning, children, expired_at = _tree(
        session,
        root_index=root_index,
        name_prefix=f"Late{root_index}",
    )
    StructuralCompressionService(session).expire_due_partners(
        expired_at + timedelta(seconds=1)
    )

    late_time = _add_calendar_months(expired_at, 3) + timedelta(seconds=1)
    _recover(session, returning, late_time)

    expected_root = roots[root_index - 1]
    assert returning.root_id == expected_root.id
    assert returning.upline_id == expected_root.id
    assert returning.lineage == [expected_root.id]
    assert session.query(PartnerRecoveryEvent).filter_by(
        partner_id=returning.id
    ).one().status == "EXPIRED"
    for child, grandchild in children:
        assert child.upline_id == parent.id
        assert child.upline_id != returning.id
        assert grandchild.upline_id == child.id

    new_child = Partner(
        first_name="New branch child",
        upline_id=returning.id,
        root_id=expected_root.id,
        lineage=[returning.id, expected_root.id],
        subscription_end_date=datetime.now(timezone.utc)
        .replace(tzinfo=None)
        + timedelta(days=365),
    )
    session.add(new_child)
    session.flush()
    assert new_child.lineage == [returning.id, expected_root.id]
    session.close()


def test_recovery_conflict_is_reported_without_reparenting_snapshot_children(
    isolated_database,
):
    session = isolated_database()
    _, parent, returning, children, expired_at = _tree(session)
    StructuralCompressionService(session).expire_due_partners(
        expired_at + timedelta(seconds=1)
    )
    child, _ = children[0]
    child.placement_version += 1
    session.flush()
    purchase_time = expired_at + timedelta(days=20)
    returning.status = PartnerStatus.ACTIVE
    returning.subscription_end_date = purchase_time + timedelta(days=30)
    purchase = Purchase(
        purchase_number="RECOVERY-CONFLICT",
        partner_id=returning.id,
        amount=Decimal("3000.00"),
        status=OrderStatus.PAID,
        paid_at=purchase_time,
    )
    session.add(purchase)
    session.flush()

    with pytest.raises(RecoveryConflictError, match="placement changed"):
        StructuralCompressionService(session).process_paid_purchase(
            returning,
            purchase,
        )

    assert child.upline_id == parent.id
    assert returning.upline_id is None
    session.rollback()
    session.close()


def test_compression_does_not_change_financial_history(isolated_database):
    session = isolated_database()
    _, parent, returning, children, expired_at = _tree(session)
    child, _ = children[0]
    historical_purchase = Purchase(
        purchase_number="HISTORICAL-COMPRESSION",
        partner_id=child.id,
        amount=Decimal("5100.00"),
        status=OrderStatus.PAID,
        paid_at=expired_at - timedelta(days=3),
    )
    session.add(historical_purchase)
    session.flush()
    commission = Commission(
        partner_id=parent.id,
        purchase_id=historical_purchase.id,
        source_partner_id=child.id,
        level=1,
        rate=Decimal("0.20"),
        base_amount=Decimal("5100.00"),
        amount=Decimal("1020.00"),
        status=CommissionStatus.APPROVED,
    )
    balance = Balance(partner_id=parent.id, amount=Decimal("1020.00"))
    session.add_all([commission, balance])
    session.flush()
    transaction = BalanceTransaction(
        partner_id=parent.id,
        amount=Decimal("1020.00"),
        type=BalanceTransactionType.COMMISSION,
        reference_id=commission.id,
        description="Historical commission",
    )
    session.add(transaction)
    session.flush()
    purchase_id, commission_id, transaction_id = (
        historical_purchase.id,
        commission.id,
        transaction.id,
    )

    StructuralCompressionService(session).expire_due_partners(
        expired_at + timedelta(seconds=1)
    )

    assert session.get(Purchase, purchase_id).amount == Decimal("5100.00")
    assert session.get(Commission, commission_id).amount == Decimal("1020.00")
    assert session.get(BalanceTransaction, transaction_id).amount == Decimal(
        "1020.00"
    )
    session.close()


def test_new_commissions_follow_current_tree_after_recovery(isolated_database):
    session = isolated_database()
    roots, parent, returning, children, expired_at = _tree(session)
    child, _ = children[0]
    service = StructuralCompressionService(session)
    service.expire_due_partners(expired_at + timedelta(seconds=1))

    results_while_inactive = CommissionCalculator(
        session,
        bot=None,
    ).calculate_purchase_commissions(
        Decimal("1000.00"),
        child.id,
        child.lineage,
    )
    assert all(result.partner_id != returning.id for result in results_while_inactive)

    _recover(session, returning, expired_at + timedelta(days=20))
    results_after_recovery = CommissionCalculator(
        session,
        bot=None,
    ).calculate_purchase_commissions(
        Decimal("1000.00"),
        child.id,
        child.lineage,
    )
    assert [result.partner_id for result in results_after_recovery] == [
        returning.id,
        parent.id,
        roots[1].id,
    ]
    session.close()


def test_order_webhook_recovery_is_idempotent(isolated_database, monkeypatch):
    session = isolated_database()
    roots, parent, returning, children, expired_at = _tree(
        session,
        name_prefix="WebhookRecovery",
    )
    partner_id = returning.id
    parent_id = parent.id
    root_id = roots[1].id
    child_ids = [child.id for child, _ in children]
    partner_email = returning.email
    partner_first_name = returning.first_name
    session.commit()
    session.close()
    monkeypatch.setattr(
        "services.order_processor.SessionLocal",
        isolated_database,
    )
    payload = {
        "id": "recovery-order-once",
        "customer_id": 7,
        "total": "3000.00",
        "status": "completed",
        "date_paid_gmt": datetime.now(timezone.utc)
        .replace(tzinfo=None)
        .isoformat(),
        "billing": {
            "email": partner_email,
            "first_name": partner_first_name,
        },
    }
    processor = OrderProcessor()
    assert asyncio.run(processor.process_order_data(payload)) is True

    session = isolated_database()
    current = session.get(Partner, partner_id)
    assert current.upline_id == parent_id
    assert current.root_id == root_id
    for child_id in child_ids:
        assert session.get(Partner, child_id).upline_id == partner_id
    assert session.query(Purchase).filter_by(
        ext_ref="recovery-order-once"
    ).count() == 1
    session.close()

    assert asyncio.run(processor.process_order_data(payload)) is True
    session = isolated_database()
    assert session.query(Purchase).filter_by(
        ext_ref="recovery-order-once"
    ).count() == 1
    assert session.get(Partner, partner_id).upline_id == parent_id
    session.close()


def test_webhook_failure_rolls_back_recovery_tree_and_purchase(
    isolated_database,
    monkeypatch,
):
    session = isolated_database()
    _, parent, returning, children, expired_at = _tree(
        session,
        name_prefix="RecoveryRollback",
    )
    partner_id = returning.id
    parent_id = parent.id
    child_ids = [child.id for child, _ in children]
    partner_email = returning.email
    session.commit()
    session.close()
    monkeypatch.setattr(
        "services.order_processor.SessionLocal",
        isolated_database,
    )

    async def fail_commissions(self, purchase):
        raise RuntimeError("simulated commission processing failure")

    monkeypatch.setattr(
        "services.order_processor.CommissionCalculator.process_purchase",
        fail_commissions,
    )
    payload = {
        "id": "recovery-order-rollback",
        "customer_id": 8,
        "total": "3000.00",
        "status": "completed",
        "date_paid_gmt": datetime.now(timezone.utc)
        .replace(tzinfo=None)
        .isoformat(),
        "billing": {"email": partner_email, "first_name": "Rollback"},
    }

    assert asyncio.run(OrderProcessor().process_order_data(payload)) is False

    session = isolated_database()
    assert session.get(Partner, partner_id).upline_id == parent_id
    assert session.get(Partner, partner_id).status == PartnerStatus.ACTIVE
    assert all(
        session.get(Partner, child_id).upline_id == partner_id
        for child_id in child_ids
    )
    assert session.query(Purchase).filter_by(
        ext_ref="recovery-order-rollback"
    ).count() == 0
    assert session.query(PartnerRecoveryEvent).filter_by(
        partner_id=partner_id
    ).count() == 0
    session.close()


def test_scheduler_runs_structural_compression(isolated_database, monkeypatch):
    session = isolated_database()
    _, parent, returning, children, expired_at = _tree(
        session,
        name_prefix="SchedulerCompression",
    )
    partner_id = returning.id
    parent_id = parent.id
    child_ids = [child.id for child, _ in children]
    session.commit()
    session.close()
    monkeypatch.setattr(scheduler, "SessionLocal", isolated_database)

    scheduler.expire_statuses()

    session = isolated_database()
    assert session.get(Partner, partner_id).upline_id is None
    assert all(
        session.get(Partner, child_id).upline_id == parent_id
        for child_id in child_ids
    )
    session.close()


def test_legacy_schema_backfills_root_id_without_rewriting_tree():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE partners ("
                "id INTEGER PRIMARY KEY, "
                "upline_id INTEGER, "
                "lineage JSON)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO partners (id, upline_id, lineage) VALUES "
                "(1, NULL, '[]'), "
                "(2, 1, '[1]'), "
                "(3, 2, '[2, 1]')"
            )
        )

    upgrade_schema(engine)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT id, upline_id, lineage, root_id, placement_version "
                "FROM partners ORDER BY id"
            )
        ).all()

    assert rows == [
        (1, None, "[]", 1, 0),
        (2, 1, "[1]", 1, 0),
        (3, 2, "[2, 1]", 1, 0),
    ]
    engine.dispose()
