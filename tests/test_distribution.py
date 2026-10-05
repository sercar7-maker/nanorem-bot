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