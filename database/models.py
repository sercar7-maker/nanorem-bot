"""Database Models for NANOREM MLM System using SQLAlchemy"""

from datetime import datetime
import enum
import uuid

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey,
    Enum as SQLEnum, Text, Boolean, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID

from database.base import Base


class PartnerRole(enum.Enum):
    PARTNER = "partner"
    ADMIN = "admin"


class PartnerStatus(enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


class OrderStatus(enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    CANCELLED = "cancelled"


class CommissionStatus(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    PAID = "paid"
    CANCELLED = "cancelled"


class WithdrawalStatus(enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    REJECTED = "rejected"


class Partner(Base):
    __tablename__ = "partners"

    id = Column(Integer, primary_key=True)

    telegram_id = Column(String, unique=True, nullable=True)
    telegram_link_code = Column(String, unique=True)

    first_name = Column(String)
    last_name = Column(String)
    username = Column(String)
    email = Column(String)
    phone = Column(String)

    upline_id = Column(Integer, ForeignKey("partners.id"), index=True)

    status = Column(
        SQLEnum(PartnerStatus),
        default=PartnerStatus.ACTIVE,
        index=True
    )

    registration_date = Column(DateTime, server_default=func.now())
    subscription_end_date = Column(DateTime, nullable=True)

    lineage = Column(JSON, default=list)

    role = Column(String, default=PartnerRole.PARTNER.value)

    upline = relationship("Partner", remote_side=[id], backref="downline")

    purchases = relationship("Purchase", back_populates="partner")

    commissions_received = relationship(
        "Commission",
        foreign_keys="Commission.partner_id",
        back_populates="partner",
    )

    commissions_generated = relationship(
        "Commission",
        foreign_keys="Commission.source_partner_id",
    )

    balance = relationship(
        "Balance",
        back_populates="partner",
        uselist=False,
    )

    withdrawals = relationship(
        "Withdrawal",
        back_populates="partner",
    )


class Purchase(Base):
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True)

    purchase_number = Column(String(50), unique=True, nullable=False)

    partner_id = Column(
        Integer,
        ForeignKey("partners.id"),
        nullable=False,
        index=True,
    )

    amount = Column(Float, nullable=False)

    currency = Column(String(10), default="RUB")

    status = Column(
        SQLEnum(OrderStatus),
        default=OrderStatus.PENDING,
    )

    ext_ref = Column(String(100))

    created_at = Column(DateTime, default=datetime.utcnow)

    paid_at = Column(DateTime)

    partner = relationship(
        "Partner",
        back_populates="purchases",
    )

    commissions = relationship(
        "Commission",
        back_populates="purchase",
    )


class Commission(Base):
    __tablename__ = "commissions"

    id = Column(Integer, primary_key=True)

    partner_id = Column(
        Integer,
        ForeignKey("partners.id"),
        nullable=False,
        index=True,
    )

    purchase_id = Column(
        Integer,
        ForeignKey("purchases.id"),
        nullable=False,
        index=True,
    )

    source_partner_id = Column(
        Integer,
        ForeignKey("partners.id"),
    )

    level = Column(Integer, nullable=False)

    rate = Column(Float, nullable=False)

    base_amount = Column(Float, nullable=False)

    amount = Column(Float, nullable=False)

    status = Column(
        SQLEnum(CommissionStatus),
        default=CommissionStatus.PENDING,
        index=True,
    )

    is_compressed = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    approved_at = Column(DateTime)

    paid_at = Column(DateTime)

    notes = Column(Text)

    partner = relationship(
        "Partner",
        foreign_keys=[partner_id],
        back_populates="commissions_received",
    )

    purchase = relationship(
        "Purchase",
        back_populates="commissions",
    )

    source_partner = relationship(
        "Partner",
        foreign_keys=[source_partner_id],
        back_populates="commissions_generated",
    )


class ConsentVersion(Base):
    __tablename__ = "consent_versions"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    version = Column(String(20), unique=True, nullable=False)

    file_path = Column(String(255), nullable=False)

    hash = Column(String(64), nullable=False)

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )


class Withdrawal(Base):
    __tablename__ = "withdrawals"

    id = Column(Integer, primary_key=True)

    partner_id = Column(
        Integer,
        ForeignKey("partners.id"),
        nullable=False,
        index=True,
    )

    amount = Column(Float, nullable=False)

    method = Column(String, nullable=False)

    details = Column(JSON, nullable=False)

    status = Column(
        SQLEnum(WithdrawalStatus),
        default=WithdrawalStatus.PENDING
    )

    created_at = Column(DateTime, default=datetime.utcnow)

    processed_at = Column(DateTime)

    admin_comment = Column(Text)

    partner = relationship(
        "Partner",
        back_populates="withdrawals",
    )


from .user_models import User

from database.models_balance import (
    Balance,
    BalanceTransaction,
    BalanceTransactionType,
)