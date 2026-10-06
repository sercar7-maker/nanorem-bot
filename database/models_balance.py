from sqlalchemy import (
    Column,
    Integer,
    Numeric,
    String,
    DateTime,
    ForeignKey,
    Enum as SQLAlchemyEnum,
    func,
    Index,
    text,
)

from sqlalchemy.orm import relationship
from enum import Enum

from database.base import Base


class BalanceTransactionType(Enum):
    COMMISSION = "commission"
    WITHDRAWAL = "withdrawal"
    ADJUSTMENT = "adjustment"


class Balance(Base):

    __tablename__ = "balances"

    partner_id = Column(
        Integer,
        ForeignKey("partners.id"),
        primary_key=True
    )

    amount = Column(
        Numeric(18, 2),
        nullable=False,
        default=0
    )

    hold = Column(
        Numeric(18, 2),
        nullable=False,
        default=0
    )

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
    __table_args__ = (
        Index(
            "uq_balance_tx_commission_reference",
            "partner_id",
            "reference_id",
            unique=True,
            sqlite_where=text(
                "type = 'COMMISSION' AND reference_id IS NOT NULL"
            ),
            postgresql_where=text(
                "type = 'COMMISSION' AND reference_id IS NOT NULL"
            ),
        ),
    )

    id = Column(Integer, primary_key=True)

    partner_id = Column(
        Integer,
        ForeignKey("balances.partner_id"),
        nullable=False,
        index=True
    )

    amount = Column(
        Numeric(18, 2),
        nullable=False
    )

    type = Column(
        SQLAlchemyEnum(BalanceTransactionType),
        nullable=False
    )

    description = Column(String)

    # 🔥 НОВЫЕ ПОЛЯ
    reference_id = Column(Integer, nullable=True)
    external_id = Column(String, nullable=True)

    created_at = Column(
        DateTime,
        server_default=func.now()
    )

    balance = relationship(
        "Balance",
        back_populates="transactions"
    )