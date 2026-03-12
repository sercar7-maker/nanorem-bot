from sqlalchemy import Column, Integer, Float, ForeignKey
from sqlalchemy.orm import relationship

from database.base import Base


class PartnerStats(Base):

    __tablename__ = "partner_stats"

    partner_id = Column(
        Integer,
        ForeignKey("partners.id"),
        primary_key=True
    )

    personal_turnover = Column(Float, default=0)
    network_turnover = Column(Float, default=0)

    monthly_personal_turnover = Column(Float, default=0)
    monthly_network_turnover = Column(Float, default=0)

    team_size = Column(Integer, default=0)

    partner = relationship("Partner")
    