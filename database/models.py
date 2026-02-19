"""Database Models for NANOREM MLM System using SQLAlchemy

This module defines the schema for partners, purchases (orders),
and commissions, synchronized with the core MLM logic.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum as SQLEnum, Text, Boolean, Decimal
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
    """Status for procurement/purchase orders."""
    PENDING = "pending"
    PAID = "paid"
    CANCELLED = "cancelled"


class CommissionStatus(enum.Enum):
    """Status for commission payout records."""
    PENDING = "pending"
    APPROVED = "approved"
    PAID = "paid"
    CANCELLED = "cancelled"


class Partner(Base):
    """Partner/Member in the NANOREM MLM network."""
    __tablename__ = 'partners'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String(50), unique=True, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100))
    username = Column(String(100)) # Telegram username
    email = Column(String(255), unique=True)
    phone = Column(String(50))
    
    # Hierarchy
    upline_id = Column(Integer, ForeignKey('partners.id'), nullable=True, index=True)
    status = Column(SQLEnum(PartnerStatus), default=PartnerStatus.ACTIVE, index=True)
    
    # Timestamps
    registration_date = Column(DateTime, default=datetime.utcnow)
    last_activity = Column(DateTime, default=datetime.utcnow)
    subscription_end_date = Column(DateTime) # Date until which ACTIVE status is valid
    
    # Accumulated totals (mirrors core data class)
    total_procurement = Column(Float, default=0.0)
    total_commissions = Column(Float, default=0.0)
    
    # Relationships
    upline = relationship('Partner', remote_side=[id], backref='downline')
    purchases = relationship('Purchase', back_populates='partner')
    commissions_earned = relationship('Commission', foreign_keys='Commission.partner_id', back_populates='partner')

    def __repr__(self):
        return f"<Partner(id={self.id}, name='{self.first_name}', status='{self.status}')>"


class Purchase(Base):
    """Record of a material procurement (purchase)."""
    __tablename__ = 'purchases'
    
    id = Column(Integer, primary_key=True)
    purchase_number = Column(String(50), unique=True, nullable=False)
    partner_id = Column(Integer, ForeignKey('partners.id'), nullable=False, index=True)
    
    amount = Column(Float, nullable=False) # Base for commission
    currency = Column(String(10), default='RUB')
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING)
    
    # External reference (e.g., order ID from website or shop)
    ext_ref = Column(String(100))
    
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime)
    
    partner = relationship('Partner', back_populates='purchases')
    commissions = relationship('Commission', back_populates='purchase')

    def __repr__(self):
        return f"<Purchase(id={self.id}, amount={self.amount}, status='{self.status}')>"


class Commission(Base):
    """Commission record linked to a specific purchase and structural level."""
    __tablename__ = 'commissions'
    
    id = Column(Integer, primary_key=True)
    partner_id = Column(Integer, ForeignKey('partners.id'), nullable=False, index=True)
    purchase_id = Column(Integer, ForeignKey('purchases.id'), nullable=False, index=True)
    source_partner_id = Column(Integer, ForeignKey('partners.id'))
    
    level = Column(Integer, nullable=False)    # Structural level (1-5)
    rate = Column(Float, nullable=False)     # Applied percentage (e.g. 20.0)
    base_amount = Column(Float, nullable=False) # Purchase amount
    amount = Column(Float, nullable=False)      # Calculated commission
    
    status = Column(SQLEnum(CommissionStatus), default=CommissionStatus.PENDING, index=True)
    is_compressed = Column(Boolean, default=False) # If true, payout was compressed upward
    
    created_at = Column(DateTime, default=datetime.utcnow)
    approved_at = Column(DateTime)
    paid_at = Column(DateTime)
    
    notes = Column(Text)
    
    partner = relationship('Partner', foreign_keys=[partner_id], back_populates='commissions_earned')
    purchase = relationship('Purchase', back_populates='commissions')
    source_partner = relationship('Partner', foreign_keys=[source_partner_id])

    def __repr__(self):
        return f"<Commission(to={self.partner_id}, amount={self.amount}, level={self.level})>"
