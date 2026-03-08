from sqlalchemy import (
    Column,
    Integer,
    Numeric,
    String,
    DateTime,
    ForeignKey,
    Enum as SQLAlchemyEnum,
    func
)

from sqlalchemy.orm import relationship
from enum import Enum

from database.base import Base


class BalanceTransactionType(Enum):

    COMMISSION = "commission"
    WITHDRAWAL = "withdrawal"
    CORRECTION = "correction"


class Balance(Base):

    __tablename__ = "balances"

    partner_id = Column(Integer, primary_key=True)

    amount = Column(Numeric(18, 2), nullable=False, default=0)

    hold = Column(Numeric(18, 2), nullable=False, default=0)

    transactions = relationship(
        "BalanceTransaction",
        back_populates="balance"
    )

    partner = relationship(
        "Partner",
        back_populates="balance"
    )


class BalanceTransaction(Base):

    __tablename__ = "balance_transactions"

    id = Column(Integer, primary_key=True)

    partner_id = Column(
        Integer,
        ForeignKey("balances.partner_id"),
        index=True,
        nullable=False
    )

    amount = Column(Numeric(18, 2), nullable=False)

    type = Column(
        SQLAlchemyEnum(BalanceTransactionType),
        nullable=False
    )

    reference_id = Column(Integer, nullable=True)

    external_id = Column(String, unique=True, nullable=True)

    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False
    )

    balance = relationship(
        "Balance",
        back_populates="transactions"
    )