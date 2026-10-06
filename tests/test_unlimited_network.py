from sqlalchemy.dialects import postgresql

from database.models import Partner
from services.partner_service import PartnerService
from core.network import NetworkManager
from services.network_tree_service import (
    NetworkTreeService,
    _lineage_contains,
)


def test_partner_network_traversal_includes_depth_beyond_five(
    isolated_database,
):
    session = isolated_database()
    root = Partner(first_name="Unlimited root", lineage=[])
    session.add(root)
    session.flush()

    previous = root
    for depth in range(1, 8):
        partner = Partner(
            first_name=f"Depth {depth}",
            upline_id=previous.id,
            lineage=[previous.id, *(previous.lineage or [])],
        )
        session.add(partner)
        session.flush()
        previous = partner
    root_id = root.id
    session.commit()
    session.close()

    service = PartnerService()
    levels = service.get_network_levels(root_id)
    session = isolated_database()
    try:
        network_ids = service.get_network_partner_ids(root_id, session)
    finally:
        session.close()

    assert [levels[level] for level in range(1, 6)] == [1, 1, 1, 1, 1]
    assert levels["total"] == 7
    assert len(network_ids) == 7


def test_network_manager_rejects_self_parent_and_handles_repeated_downline():
    manager = NetworkManager()

    assert manager.add_partner(1) is True
    assert manager.add_partner(2, 1) is True
    assert manager.add_partner(3, 2) is True
    assert manager.add_partner(4, 4) is False

    manager.get_partner(3).downline_ids.append(1)

    assert manager.get_downline(1, recursive=True) == [2, 3]


def test_network_tree_finds_deep_descendants_in_sqlite(isolated_database):
    session = isolated_database()
    root = Partner(first_name="Tree root", lineage=[])
    session.add(root)
    session.flush()

    child = Partner(
        first_name="Tree child",
        upline_id=root.id,
        lineage=[root.id],
    )
    session.add(child)
    session.flush()
    grandchild = Partner(
        first_name="Tree grandchild",
        upline_id=child.id,
        lineage=[child.id, root.id],
    )
    session.add(grandchild)
    session.commit()

    result = NetworkTreeService(session).get_network_tree(root.id)

    assert {item["id"] for members in result.values() for item in members} == {
        child.id,
        grandchild.id,
    }
    session.close()


def test_postgresql_lineage_filter_uses_jsonb_containment():
    compiled = str(
        _lineage_contains(123, "postgresql").compile(
            dialect=postgresql.dialect()
        )
    )

    assert "CAST(partners.lineage AS JSONB) @>" in compiled
