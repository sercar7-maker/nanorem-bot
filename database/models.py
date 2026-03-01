"""Database Models for NANOREM MLM System using SQLAlchemy

This module defines the schema for partners, purchases (orders),
and commissions, synchronized with the core MLM logic.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum as SQLEnum, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()


class PartnerStatus(enum.Enum):
    """Partner status enumeration (matches core.partner_manager)."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


class OrderStatus(enum.Enum):
    """Purchase/order status."""
    PENDING = "pending"
    PAID = "paid"
    CANCELLED = "cancelled"


class CommissionStatus(enum.Enum):
    """Commission payout record status."""
    PENDING = "pending"
    APPROVED = "approved"
    PAID = "paid"
    CANCELLED = "cancelled"


class Partner(Base):
    """Partner/Participant of the NANOREM MLM network."""
    __tablename__ = 'partners'

    id = Column(Integer, primary_key=True)
    telegram_id = Column(String(50), unique=True, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100))
    username = Column(String(100))
    email = Column(String(255), unique=True)
    phone = Column(String(50))

    # Hierarchy
    upline_id = Column(Integer, ForeignKey('partners.id'), nullable=True, index=True)
    status = Column(SQLEnum(PartnerStatus), default=PartnerStatus.INACTIVE, index=True)

    # Timestamps
    registration_date = Column(DateTime, default=datetime.utcnow)
    last_activity = Column(DateTime, default=datetime.utcnow)
    subscription_end_date = Column(DateTime)

    # Accumulated totals
    total_procurement = Column(Float, default=0.0)
    total_commissions = Column(Float, default=0.0)

    # Relationships
    upline = relationship('Partner', remote_side=[id], backref='downline')
    purchases = relationship('Purchase', back_populates='partner')
    commissions_earned = relationship('Commission', foreign_keys='Commission.partner_id', back_populates='partner')

    def __repr__(self):
        return f"<Partner id={self.id} telegram_id={self.telegram_id} status={self.status}>"


class Purchase(Base):
    """Purchase/procurement record."""
    __tablename__ = 'purchases'

    id = Column(Integer, primary_key=True)
    purchase_number = Column(String(50), unique=True, nullable=False)
    partner_id = Column(Integer, ForeignKey('partners.id'), nullable=False, index=True)

    amount = Column(Float, nullable=False)
    currency = Column(String(10), default='RUB')
    status = Column(String(20), default='pending')

    ext_ref = Column(String(100))

    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime)

    partner = relationship('Partner', back_populates='purchases')
    commissions = relationship('Commission', back_populates='purchase')

    def __repr__(self):
        return f"<Purchase id={self.id} amount={self.amount} status={self.status}>"


class Commission(Base):
    """Commission payout record linked to a specific purchase and upline level."""
    __tablename__ = 'commissions'

    id = Column(Integer, primary_key=True)
    partner_id = Column(Integer, ForeignKey('partners.id'), nullable=False, index=True)
    purchase_id = Column(Integer, ForeignKey('purchases.id'), nullable=False, index=True)
    source_partner_id = Column(Integer, ForeignKey('partners.id'))

    level = Column(Integer, nullable=False)
    rate = Column(Float, nullable=False)
    base_amount = Column(Float, nullable=False)
    amount = Column(Float, nullable=False)

    status = Column(SQLEnum(CommissionStatus), default=CommissionStatus.PENDING, index=True)
    is_compressed = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    approved_at = Column(DateTime)
    paid_at = Column(DateTime)

    notes = Column(Text)

    partner = relationship('Partner', foreign_keys=[partner_id], back_populates='commissions_earned')
    purchase = relationship('Purchase', back_populates='commissions')
    source_partner = relationship('Partner', foreign_keys=[source_partner_id])

    def __repr__(self):
        return f"<Commission id={self.id} level={self.level} amount={self.amount}>"
