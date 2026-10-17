"""Cabinet contacts; not connected to the current login flow."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from database.models import Base
from database.models_cabinet import CabinetOwner  # noqa: F401


class CabinetContact(Base):
    __tablename__ = "cabinet_contacts"
    __table_args__ = (
        UniqueConstraint(
            "channel",
            "normalized_value",
            name="uq_cabinet_contact_identity",
        ),
        CheckConstraint(
            "channel IN ('email', 'phone')",
            name="ck_cabinet_contact_channel",
        ),
    )

    id = Column(Integer, primary_key=True)
    owner_id = Column(
        Integer,
        ForeignKey("cabinet_owners.id"),
        nullable=False,
        index=True,
    )
    channel = Column(String(16), nullable=False)
    normalized_value = Column(String(254), nullable=False)
    verified_at = Column(DateTime, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )