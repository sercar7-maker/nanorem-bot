from datetime import datetime, timedelta

from database.models import Partner, PartnerStatus
from scheduler import expire_statuses
import scheduler


def test_expire_statuses_only_deactivates_overdue_subscriptions(
    isolated_database,
    monkeypatch,
):
    session = isolated_database()
    partners = [
        Partner(
            first_name="Expired subscription",
            status=PartnerStatus.ACTIVE,
            subscription_end_date=datetime.utcnow() - timedelta(seconds=1),
        ),
        Partner(
            first_name="Current subscription",
            status=PartnerStatus.ACTIVE,
            subscription_end_date=datetime.utcnow() + timedelta(days=1),
        ),
        Partner(
            first_name="No subscription expiry",
            status=PartnerStatus.ACTIVE,
        ),
        Partner(
            first_name="Already inactive",
            status=PartnerStatus.INACTIVE,
            subscription_end_date=datetime.utcnow() - timedelta(days=1),
        ),
    ]
    session.add_all(partners)
    session.commit()
    partner_ids = [partner.id for partner in partners]
    session.close()
    monkeypatch.setattr(scheduler, "SessionLocal", isolated_database)

    expire_statuses()

    session = isolated_database()
    try:
        statuses = [
            session.get(Partner, partner_id).status
            for partner_id in partner_ids
        ]
    finally:
        session.close()

    assert statuses == [
        PartnerStatus.INACTIVE,
        PartnerStatus.ACTIVE,
        PartnerStatus.ACTIVE,
        PartnerStatus.INACTIVE,
    ]
