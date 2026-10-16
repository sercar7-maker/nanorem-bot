"""Explicit ownership preparation. No default engine or startup hook."""

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from database.models import Partner
from database.models_cabinet import CabinetOwner, CabinetPosition


def create_cabinet_schema(engine) -> None:
    """Create only the two additive ownership tables on the supplied engine."""
    with engine.begin() as connection:
        if not inspect(connection).has_table("partners"):
            raise RuntimeError("The partners table must exist first")
        CabinetOwner.__table__.create(connection, checkfirst=True)
        CabinetPosition.__table__.create(connection, checkfirst=True)


def backfill_cabinet_owners(session: Session) -> int:
    """Prepare one owner per unlinked partner; caller commits or rolls back.

    Run offline on a reviewed database copy first. Never merge by contact.
    Does not create positions, change partners, or update authentication.
    """
    created = 0
    with session.begin_nested():
        partners = session.query(Partner).order_by(Partner.id).all()
        for partner in partners:
            if session.get(CabinetPosition, partner.id) is not None:
                continue
            owner = (
                session.query(CabinetOwner)
                .filter(CabinetOwner.primary_partner_id == partner.id)
                .one_or_none()
            )
            if owner is None:
                owner = CabinetOwner(primary_partner_id=partner.id)
                session.add(owner)
                session.flush()
                created += 1
            session.add(CabinetPosition(partner_id=partner.id, owner_id=owner.id))
        session.flush()
    return created
