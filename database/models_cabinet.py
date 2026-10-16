"""Cabinet ownership foundation; not used by the current login flow."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer
from sqlalchemy.sql import func

from database.models import Base


class CabinetOwner(Base):
    __tablename__ = "cabinet_owners"

    id = Column(Integer, primary_key=True)
    primary_partner_id = Column(
        Integer, ForeignKey("partners.id"), nullable=False, unique=True
    )
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class CabinetPosition(Base):
    __tablename__ = "cabinet_positions"

    partner_id = Column(Integer, ForeignKey("partners.id"), primary_key=True)
    owner_id = Column(
        Integer, ForeignKey("cabinet_owners.id"), nullable=False, index=True
    )
