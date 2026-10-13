import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Partner
from services.distribution_service import DistributionService
from services.partner_service import PartnerService
from services.order_processor import OrderProcessor


def create_test_session():
    engine = create_engine("sqlite:///:memory:")
    Partner.__table__.create(engine)

    Session = sessionmaker(bind=engine)
    return Session()


def build_test_network(session):
    root1 = Partner(
        first_name="Distribution Root 1",
        username="distribution_root_1",
        lineage=[],
    )
    root2 = Partner(
        first_name="Distribution Root 2",
        username="distribution_root_2",
        lineage=[],
    )

    session.add_all([root1, root2])
    session.flush()

    # Root 1: большая сеть.
    parent = Partner(
        first_name="Root1 A",
        username="root1_a",
        upline_id=root1.id,
        lineage=[root1.id],
    )
    session.add(parent)
    session.flush()

    previous = parent

    for index in range(8):
        partner = Partner(
            first_name=f"Root1 {index}",
            username=f"root1_{index}",
            upline_id=previous.id,
            lineage=[previous.id, *(previous.lineage or [])],
        )
        session.add(partner)
        session.flush()
        previous = partner

    # Root 2: маленькая сеть.
    partner_b = Partner(
        first_name="Root2 B",
        username="root2_b",
        upline_id=root2.id,
        lineage=[root2.id],
    )
    partner_c = Partner(
        first_name="Root2 C",
        username="root2_c",
        upline_id=root2.id,
        lineage=[root2.id],
    )

    session.add_all([partner_b, partner_c])
    session.flush()

    partner_d = Partner(
        first_name="Root2 D",
        username="root2_d",
        upline_id=partner_b.id,
        lineage=[partner_b.id, root2.id],
    )

    session.add(partner_d)
    session.flush()

    return root1, root2


def test_distribution_service_chooses_smaller_root_network():
    session = create_test_session()

    try:
        root1, root2 = build_test_network(session)

        selected_root_id = DistributionService().get_upline_for_new_partner(
            session
        )

        assert selected_root_id == root2.id

    finally:
        session.rollback()
        session.close()


def test_partner_service_uses_distribution_service_for_root_selection():
    session = create_test_session()

    try:
        root1, root2 = build_test_network(session)

        selected_root_id = PartnerService().choose_root(session)

        assert selected_root_id == root2.id

    finally:
        session.rollback()
        session.close()


def test_order_processor_uses_distribution_service_for_root_selection():
    session = create_test_session()

    try:
        root1, root2 = build_test_network(session)

        processor = OrderProcessor.__new__(OrderProcessor)

        selected_root_id = processor._choose_root_for_new_partner(session)

        assert selected_root_id == root2.id

    finally:
        session.rollback()
        session.close()


def add_root_pair(session, prefix):
    lower = Partner(
        first_name=f"{prefix} root 1",
        username=f"{prefix}_root_1",
        lineage=[],
    )
    higher = Partner(
        first_name=f"{prefix} root 2",
        username=f"{prefix}_root_2",
        lineage=[],
    )
    session.add_all([lower, higher])
    session.flush()
    return lower, higher


def add_lineage_members(session, root, count, label):
    members = [
        Partner(
            first_name=f"{label} {index}",
            username=f"{label}_{index}",
            upline_id=root.id,
            lineage=[root.id],
        )
        for index in range(count)
    ]
    session.add_all(members)
    session.flush()
    return members


def test_equal_nonzero_networks_select_higher_root_id():
    session = create_test_session()

    try:
        lower, higher = add_root_pair(session, "equal")
        assert higher.id > lower.id
        add_lineage_members(session, lower, 2, "equal_lower")
        add_lineage_members(session, higher, 2, "equal_higher")

        selected_root_id = DistributionService().get_upline_for_new_partner(
            session
        )

        assert selected_root_id == higher.id

    finally:
        session.rollback()
        session.close()


def test_empty_networks_select_higher_root_id():
    session = create_test_session()

    try:
        lower, higher = add_root_pair(session, "empty")
        assert higher.id > lower.id

        selected_root_id = DistributionService().get_upline_for_new_partner(
            session
        )

        assert selected_root_id == higher.id

    finally:
        session.rollback()
        session.close()


def test_next_selection_after_higher_root_goes_to_smaller_network():
    session = create_test_session()

    try:
        lower, higher = add_root_pair(session, "sequence")
        assert higher.id > lower.id

        selected_root_id = DistributionService().get_upline_for_new_partner(
            session
        )
        assert selected_root_id == higher.id

        session.add(
            Partner(
                first_name="Placed under higher",
                username="sequence_placed",
                upline_id=higher.id,
                lineage=[higher.id],
            )
        )
        session.flush()

        assert (
            DistributionService().get_upline_for_new_partner(session)
            == lower.id
        )

    finally:
        session.rollback()
        session.close()


def test_third_root_is_rejected():
    session = create_test_session()

    try:
        add_root_pair(session, "extra")
        session.add(
            Partner(
                first_name="extra root 3",
                username="extra_root_3",
                lineage=[],
            )
        )
        session.flush()

        with pytest.raises(ValueError, match="Нужно ровно 2 root-партнёра"):
            DistributionService().get_upline_for_new_partner(session)

    finally:
        session.rollback()
        session.close()


def test_partner_service_and_order_processor_match_distribution_on_tie():
    session = create_test_session()

    try:
        lower, higher = add_root_pair(session, "callers")
        assert higher.id > lower.id
        add_lineage_members(session, lower, 2, "callers_lower")
        add_lineage_members(session, higher, 2, "callers_higher")

        selected_root_id = DistributionService().get_upline_for_new_partner(
            session
        )
        processor = OrderProcessor.__new__(OrderProcessor)

        assert selected_root_id == higher.id
        assert PartnerService().choose_root(session) == selected_root_id
        assert (
            processor._choose_root_for_new_partner(session)
            == selected_root_id
        )

    finally:
        session.rollback()
        session.close()