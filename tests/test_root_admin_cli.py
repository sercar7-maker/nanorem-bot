from datetime import datetime

import pytest

from database.models import Partner, PartnerStatus
from root_admin_cli import (
    GrantRefused,
    database_label,
    grant_admin,
    show_roots,
)


def _add_root(
    session,
    *,
    first_name: str,
    role: str = "partner",
    email: str | None = None,
) -> Partner:
    partner = Partner(
        first_name=first_name,
        last_name="Operator",
        email=email or f"{first_name}@example.test",
        phone="+15550001001",
        upline_id=None,
        lineage=[],
        role=role,
        status=PartnerStatus.ACTIVE,
    )
    session.add(partner)
    session.flush()
    partner.root_id = partner.id
    session.commit()
    session.refresh(partner)
    return partner


def _snapshot(session) -> list[tuple]:
    rows = session.query(Partner).order_by(Partner.id).all()
    return [
        (
            row.id,
            row.first_name,
            row.last_name,
            row.email,
            row.phone,
            row.role,
            row.status,
            row.root_id,
            row.upline_id,
            row.lineage,
            row.subscription_end_date,
            row.annual_activity_until,
        )
        for row in rows
    ]


def test_database_label_omits_credentials():
    label = database_label(
        "postgresql://audit_user:do-not-print@db.example:5432/nanorem"
    )

    assert label == "dialect=postgresql host=db.example database=nanorem"
    assert "do-not-print" not in label
    assert "audit_user" not in label
    assert "postgresql://" not in label


def test_show_lists_permanent_roots_without_changing_them(isolated_database):
    session = isolated_database()
    first = _add_root(session, first_name="RootOne")
    second = _add_root(session, first_name="RootTwo")
    before = _snapshot(session)

    output = show_roots(session, "sqlite://")

    assert "dialect=sqlite path=:memory:" in output
    assert f"id={first.id}" in output
    assert f"id={second.id}" in output
    assert "role=partner" in output
    assert _snapshot(session) == before
    session.close()


def test_dry_run_does_not_change_the_selected_root(isolated_database):
    session = isolated_database()
    first = _add_root(session, first_name="DryRoot")
    _add_root(session, first_name="OtherRoot")
    before = _snapshot(session)

    message = grant_admin(session, first.id, apply=False)

    assert message.startswith("dry-run:")
    assert f"Partner {first.id}" in message
    assert _snapshot(session) == before
    session.close()


def test_apply_sets_only_the_selected_root_role(isolated_database):
    session = isolated_database()
    selected = _add_root(session, first_name="Selected")
    other = _add_root(session, first_name="Unchanged")
    before = {
        row.id: _snapshot(session)[index]
        for index, row in enumerate(
            session.query(Partner).order_by(Partner.id).all()
        )
    }

    message = grant_admin(session, selected.id, apply=True)

    session.refresh(selected)
    session.refresh(other)
    assert message == (
        f"Updated partner {selected.id}: role 'partner' -> 'admin'"
    )
    assert selected.role == "admin"
    assert other.role == "partner"
    selected_before = before[selected.id]
    other_before = before[other.id]
    assert selected.root_id == selected_before[7]
    assert selected.upline_id == selected_before[8]
    assert selected.lineage == selected_before[9]
    assert selected.status == selected_before[6]
    assert selected.subscription_end_date == selected_before[10]
    assert selected.annual_activity_until == selected_before[11]
    assert selected.first_name == selected_before[1]
    assert other.root_id == other_before[7]
    assert other.upline_id == other_before[8]
    session.close()


def test_missing_partner_and_non_root_are_refused(isolated_database):
    session = isolated_database()
    root = _add_root(session, first_name="OnlyRoot")
    _add_root(session, first_name="SecondRoot")
    child = Partner(
        first_name="Child",
        upline_id=root.id,
        root_id=root.id,
        lineage=[root.id],
        role="partner",
        status=PartnerStatus.ACTIVE,
    )
    session.add(child)
    session.commit()
    before = _snapshot(session)

    with pytest.raises(GrantRefused, match="was not found"):
        grant_admin(session, 999999, apply=True)
    with pytest.raises(GrantRefused, match="is not a permanent Root"):
        grant_admin(session, child.id, apply=True)

    assert _snapshot(session) == before
    session.close()


@pytest.mark.parametrize("root_count", [0, 1, 3])
def test_grant_refuses_when_permanent_root_count_is_not_two(
    isolated_database,
    root_count,
):
    session = isolated_database()
    created = [
        _add_root(session, first_name=f"Count{index}")
        for index in range(root_count)
    ]
    target_id = created[0].id if created else 1
    before = _snapshot(session)

    with pytest.raises(GrantRefused, match="Expected exactly 2 permanent Roots"):
        grant_admin(session, target_id, apply=True)

    assert _snapshot(session) == before
    session.close()


def test_grant_refuses_when_another_admin_exists(isolated_database):
    session = isolated_database()
    existing = _add_root(
        session,
        first_name="ExistingAdmin",
        role="admin",
    )
    candidate = _add_root(session, first_name="Candidate")
    before = _snapshot(session)

    with pytest.raises(
        GrantRefused,
        match=f"Another partner already has role admin: {existing.id}",
    ):
        grant_admin(session, candidate.id, apply=True)

    assert _snapshot(session) == before
    session.close()


def test_repeat_grant_for_the_same_admin_makes_no_change(isolated_database):
    session = isolated_database()
    admin = _add_root(session, first_name="AlreadyAdmin", role="admin")
    other = _add_root(session, first_name="StillPartner")
    before = _snapshot(session)

    dry_run = grant_admin(session, admin.id, apply=False)
    applied = grant_admin(session, admin.id, apply=True)

    session.refresh(admin)
    session.refresh(other)
    assert dry_run == f"Partner {admin.id} is already admin; no change"
    assert applied == f"Partner {admin.id} is already admin; no change"
    assert admin.role == "admin"
    assert other.role == "partner"
    assert _snapshot(session) == before
    assert other.subscription_end_date is None
    assert admin.annual_activity_until is None
    assert isinstance(admin.registration_date, datetime) or (
        admin.registration_date is None
    )
    session.close()
