"""Regression tests: permanent Root partners are always active.

Approved rules: exactly two permanent Root partners exist; Root partners are
not deactivated by a missing subscription, are not structurally compressed and
receive regular 20/10/5/5/5 commissions when they sit in a paid level.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock

from core.commission import CommissionCalculator
from database.models import Partner, PartnerRecoveryEvent, PartnerStatus
from services.partner_service import PartnerService
from services.structural_compression_service import (
    StructuralCompressionService,
)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _create_root_pair(isolated_database):
    service = PartnerService()
    first = service.create_root(first_name="Permanent Root 1")
    second = service.create_root(first_name="Permanent Root 2")
    return first.id, second.id


def _regular_partner(session, *, upline, subscription_end_date, name):
    partner = Partner(
        first_name=name,
        status=PartnerStatus.ACTIVE,
        upline_id=upline.id,
        root_id=upline.root_id,
        lineage=[upline.id] + list(upline.lineage or []),
        subscription_end_date=subscription_end_date,
    )
    session.add(partner)
    session.flush()
    return partner


def test_root_without_subscription_is_active(isolated_database):
    root_ids = _create_root_pair(isolated_database)

    session = isolated_database()
    try:
        for root_id in root_ids:
            root = session.get(Partner, root_id)
            assert root.subscription_end_date is None
            assert root.root_id == root.id
            assert root.upline_id is None
            assert root.is_permanent_root is True
            assert root.is_active is True
    finally:
        session.close()


def test_root_with_expired_subscription_is_still_active(isolated_database):
    root_id, _ = _create_root_pair(isolated_database)

    session = isolated_database()
    try:
        root = session.get(Partner, root_id)
        root.subscription_end_date = _now() - timedelta(days=30)
        session.flush()
        assert root.is_active is True
    finally:
        session.close()


def test_root_receives_level_one_commission(isolated_database):
    root_id, _ = _create_root_pair(isolated_database)

    session = isolated_database()
    try:
        root = session.get(Partner, root_id)
        buyer = _regular_partner(
            session,
            upline=root,
            subscription_end_date=_now() + timedelta(days=30),
            name="Buyer under Root",
        )

        results = CommissionCalculator(
            session, Mock()
        ).calculate_purchase_commissions(
            purchase_amount=Decimal("1000.00"),
            buying_partner_id=buyer.id,
            lineage=buyer.lineage,
        )

        assert [(r.partner_id, r.level, r.rate, r.amount) for r in results] == [
            (root.id, 1, Decimal("0.20"), Decimal("200.00")),
        ]
    finally:
        session.close()


def test_root_receives_commission_on_its_level_in_five_level_chain(
    isolated_database,
):
    root_id, _ = _create_root_pair(isolated_database)

    session = isolated_database()
    try:
        root = session.get(Partner, root_id)
        active_until = _now() + timedelta(days=30)
        upline = root
        chain = []
        for index in range(1, 5):
            upline = _regular_partner(
                session,
                upline=upline,
                subscription_end_date=active_until,
                name=f"Level partner {index}",
            )
            chain.append(upline)
        buyer = _regular_partner(
            session,
            upline=upline,
            subscription_end_date=active_until,
            name="Five-level buyer",
        )

        results = CommissionCalculator(
            session, Mock()
        ).calculate_purchase_commissions(
            purchase_amount=Decimal("1000.00"),
            buying_partner_id=buyer.id,
            lineage=buyer.lineage,
        )

        expected_recipients = [p.id for p in reversed(chain)] + [root.id]
        assert [r.partner_id for r in results] == expected_recipients
        assert [r.level for r in results] == [1, 2, 3, 4, 5]
        assert [r.rate for r in results] == [
            Decimal("0.20"),
            Decimal("0.10"),
            Decimal("0.05"),
            Decimal("0.05"),
            Decimal("0.05"),
        ]
        root_result = results[-1]
        assert root_result.partner_id == root.id
        assert root_result.level == 5
        assert root_result.amount == Decimal("50.00")
    finally:
        session.close()


def test_regular_partner_without_valid_subscription_is_not_active(
    isolated_database,
):
    root_id, _ = _create_root_pair(isolated_database)

    session = isolated_database()
    try:
        root = session.get(Partner, root_id)
        no_subscription = _regular_partner(
            session,
            upline=root,
            subscription_end_date=None,
            name="No subscription",
        )
        expired = _regular_partner(
            session,
            upline=root,
            subscription_end_date=_now() - timedelta(days=1),
            name="Expired subscription",
        )
        # A compressed regular partner is detached (upline_id=None) but keeps
        # its root affiliation; it must not be mistaken for a Root.
        detached = _regular_partner(
            session,
            upline=root,
            subscription_end_date=None,
            name="Detached regular partner",
        )
        detached.upline_id = None
        detached.lineage = []
        session.flush()

        for partner in (no_subscription, expired, detached):
            assert partner.is_permanent_root is False
            assert partner.status == PartnerStatus.ACTIVE
            assert partner.is_active is False
    finally:
        session.close()


def test_inactive_regular_partner_is_skipped_and_root_moves_up(
    isolated_database,
):
    root_id, _ = _create_root_pair(isolated_database)

    session = isolated_database()
    try:
        root = session.get(Partner, root_id)
        inactive_sponsor = _regular_partner(
            session,
            upline=root,
            subscription_end_date=None,
            name="Inactive sponsor",
        )
        buyer = _regular_partner(
            session,
            upline=inactive_sponsor,
            subscription_end_date=_now() + timedelta(days=30),
            name="Buyer under inactive sponsor",
        )

        results = CommissionCalculator(
            session, Mock()
        ).calculate_purchase_commissions(
            purchase_amount=Decimal("1000.00"),
            buying_partner_id=buyer.id,
            lineage=buyer.lineage,
        )

        assert [(r.partner_id, r.level, r.amount) for r in results] == [
            (root.id, 1, Decimal("200.00")),
        ]
        assert inactive_sponsor.id not in [r.partner_id for r in results]
    finally:
        session.close()


def test_root_without_subscription_is_not_compressed(isolated_database):
    root_ids = _create_root_pair(isolated_database)

    session = isolated_database()
    try:
        service = StructuralCompressionService(session)
        assert service.expire_due_partners(_now() + timedelta(days=1)) == 0

        for root_id in root_ids:
            root = session.get(Partner, root_id)
            assert service.compress_partner(
                root,
                lost_activity_at=_now(),
            ) is False
            assert root.status == PartnerStatus.ACTIVE
            assert root.upline_id is None
            assert root.root_id == root.id
            assert root.is_active is True
            assert session.query(PartnerRecoveryEvent).filter_by(
                partner_id=root.id
            ).count() == 0
    finally:
        session.close()
