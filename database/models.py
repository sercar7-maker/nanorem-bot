"""Database Models for NANOREM MLM System using SQLAlchemy"""

from datetime import datetime, timezone
import enum
import secrets
import uuid

from sqlalchemy import (
    CheckConstraint, Column, Index, Integer, String, Numeric, DateTime,
    ForeignKey, Enum as SQLEnum, Text, Boolean, JSON, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from core.security_tokens import create_telegram_binding_token

from database.base import Base


def create_referral_code() -> str:
    return f"nr_{secrets.token_urlsafe(18)}"


class PartnerRole(enum.Enum):
    PARTNER = "partner"
    ADMIN = "admin"


class PartnerStatus(enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


class OrderStatus(enum.Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class CommissionStatus(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    PAID = "paid"
    CANCELLED = "cancelled"


class WithdrawalStatus(enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    REJECTED = "rejected"


# =========================
# PARTNER
# =========================

class Partner(Base):
    __tablename__ = "partners"

    id = Column(Integer, primary_key=True)

    telegram_id = Column(String, unique=True, nullable=True)

    telegram_link_code = Column(
        String,
        unique=True,
        default=create_telegram_binding_token
    )
    referral_code = Column(
        String(32),
        unique=True,
        nullable=False,
        default=create_referral_code,
    )

    first_name = Column(String)
    last_name = Column(String)
    username = Column(String)
    email = Column(String)
    phone = Column(String)
    consent_given = Column(Boolean, nullable=False, default=False)
    consent_version = Column(String(50), nullable=True)
    consent_date = Column(DateTime, nullable=True)

    upline_id = Column(Integer, ForeignKey("partners.id"), index=True)
    root_id = Column(Integer, ForeignKey("partners.id"), index=True)
    placement_version = Column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    status = Column(
        SQLEnum(PartnerStatus),
        default=PartnerStatus.ACTIVE,
        index=True
    )

    registration_date = Column(DateTime, server_default=func.now())
    subscription_end_date = Column(DateTime, nullable=True)
    annual_activity_until = Column(DateTime, nullable=True)

    @property
    def is_permanent_root(self) -> bool:
        return (
            self.id is not None
            and self.root_id == self.id
            and self.upline_id is None
        )

    @property
    def is_active(self) -> bool:
        if self.status not in {
            PartnerStatus.ACTIVE,
            PartnerStatus.ACTIVE.name,
            PartnerStatus.ACTIVE.value,
        }:
            return False

        # Permanent Root partners are not deactivated by a missing or
        # expired subscription; only regular partners need one.
        if self.is_permanent_root:
            return True

        subscription_end = self.subscription_end_date
        if subscription_end is None:
            return False

        if subscription_end.tzinfo is None:
            subscription_end = subscription_end.replace(tzinfo=timezone.utc)
        else:
            subscription_end = subscription_end.astimezone(timezone.utc)

        return subscription_end > datetime.now(timezone.utc)

    lineage = Column(JSON, default=list)

    role = Column(String, default=PartnerRole.PARTNER.value)

    # 🔥 ДОБАВИЛИ РАНГ (если ещё нет)
    rank = Column(String, default="Silver")

    upline = relationship(
        "Partner",
        remote_side=[id],
        foreign_keys=[upline_id],
        backref="downline",
    )

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


Index(
    "uq_partners_email_normalized",
    func.lower(Partner.email),
    unique=True,
)


class AuthChallenge(Base):
    __tablename__ = "auth_challenges"
    __table_args__ = (
        CheckConstraint(
            "channel IN ('email', 'phone')",
            name="ck_auth_challenges_channel",
        ),
        CheckConstraint(
            "purpose IN "
            "('login', 'recovery', 'change_email', 'change_phone')",
            name="ck_auth_challenges_purpose",
        ),
        CheckConstraint(
            "attempts >= 0 AND max_attempts > 0 "
            "AND attempts <= max_attempts",
            name="ck_auth_challenges_attempt_limits",
        ),
        Index("ix_auth_challenges_partner_id", "partner_id"),
        Index("ix_auth_challenges_expires_at", "expires_at"),
    )

    id = Column(Integer, primary_key=True)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=True)
    channel = Column(String(10), nullable=False)
    purpose = Column(String(20), nullable=False)
    destination = Column(String(320), nullable=False)
    code_hash = Column(String(128), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    max_attempts = Column(Integer, nullable=False, default=5, server_default="5")
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    @property
    def is_valid(self) -> bool:
        if self.used_at is not None or self.attempts >= self.max_attempts:
            return False
        expiry = self.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        else:
            expiry = expiry.astimezone(timezone.utc)
        return expiry > datetime.now(timezone.utc)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        Index("ix_auth_sessions_partner_id", "partner_id"),
        Index("ix_auth_sessions_expires_at", "expires_at"),
    )

    id = Column(Integer, primary_key=True)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=False)
    token_hash = Column(String(128), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    @property
    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        expiry = self.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        else:
            expiry = expiry.astimezone(timezone.utc)
        return expiry > datetime.now(timezone.utc)


class RootAllocationLock(Base):
    __tablename__ = "root_allocation_lock"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_root_allocation_lock_singleton"),
    )

    id = Column(Integer, primary_key=True)
    lock_version = Column(Integer, nullable=False, default=0)


class PartnerRecoveryEvent(Base):
    __tablename__ = "partner_recovery_events"

    id = Column(Integer, primary_key=True)
    partner_id = Column(
        Integer,
        ForeignKey("partners.id"),
        nullable=False,
        index=True,
    )
    root_id = Column(Integer, ForeignKey("partners.id"), nullable=False)
    old_upline_id = Column(Integer, ForeignKey("partners.id"))
    old_parent_lineage = Column(JSON, nullable=False, default=list)
    lost_activity_at = Column(DateTime, nullable=False)
    recovery_until = Column(DateTime, nullable=False)
    compressed_at = Column(DateTime, nullable=False)
    compressed_partner_version = Column(Integer, nullable=False)
    old_parent_version = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="PENDING")
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )


Index(
    "uq_partner_recovery_pending",
    PartnerRecoveryEvent.partner_id,
    unique=True,
    sqlite_where=(PartnerRecoveryEvent.status == "PENDING"),
    postgresql_where=(PartnerRecoveryEvent.status == "PENDING"),
)


class PartnerRecoveryChild(Base):
    __tablename__ = "partner_recovery_children"
    __table_args__ = (
        UniqueConstraint(
            "recovery_event_id",
            "child_partner_id",
            name="uq_partner_recovery_child",
        ),
    )

    id = Column(Integer, primary_key=True)
    recovery_event_id = Column(
        Integer,
        ForeignKey("partner_recovery_events.id"),
        nullable=False,
        index=True,
    )
    child_partner_id = Column(
        Integer,
        ForeignKey("partners.id"),
        nullable=False,
    )
    compressed_placement_version = Column(Integer, nullable=False)


# =========================
# PURCHASE = ORDER
# =========================

class Purchase(Base):
    __tablename__ = "purchases"
    __table_args__ = (
        UniqueConstraint("ext_ref", name="uq_purchases_ext_ref"),
    )

    id = Column(Integer, primary_key=True)

    purchase_number = Column(String(50), unique=True, nullable=False)

    partner_id = Column(
        Integer,
        ForeignKey("partners.id"),
        nullable=False,
        index=True,
    )

    amount = Column(Numeric(18, 2), nullable=False)

    currency = Column(String(10), default="RUB")

    status = Column(
        SQLEnum(OrderStatus),
        default=OrderStatus.PENDING,
    )

    ext_ref = Column(String(100), nullable=True)  # id заказа с сайта

    created_at = Column(DateTime, default=datetime.utcnow)

    paid_at = Column(DateTime)

    # 🔥 ДОБАВИЛИ ФЛАГ (важно для защиты от дублей)
    is_commission_processed = Column(Boolean, default=False)

    partner = relationship(
        "Partner",
        back_populates="purchases",
    )

    commissions = relationship(
        "Commission",
        back_populates="purchase",
    )


# =========================
# COMMISSION
# =========================

class Commission(Base):
    __tablename__ = "commissions"
    __table_args__ = (
        UniqueConstraint(
            "purchase_id",
            "level",
            name="uq_commissions_purchase_level",
        ),
    )

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

    rate = Column(Numeric(5, 4), nullable=False)

    base_amount = Column(Numeric(18, 2), nullable=False)

    amount = Column(Numeric(18, 2), nullable=False)

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


# =========================
# CONSENT
# =========================

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


# =========================
# WITHDRAWAL
# =========================

class Withdrawal(Base):
    __tablename__ = "withdrawals"

    id = Column(Integer, primary_key=True)

    partner_id = Column(
        Integer,
        ForeignKey("partners.id"),
        nullable=False,
        index=True,
    )

    amount = Column(Numeric(18, 2), nullable=False)

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


# =========================
# IMPORTS
# =========================

from .user_models import User

from database.models_balance import (
    Balance,
    BalanceTransaction,
    BalanceTransactionType,
)

from database.models_stats import PartnerStats