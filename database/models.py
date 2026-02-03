"""Database Models for NANOREM MLM System using SQLAlchemy"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum as SQLEnum, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()

class PartnerStatus(enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"

class OrderStatus(enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

class CommissionStatus(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    PAID = "paid"
    CANCELLED = "cancelled"

class Partner(Base):
    """Partner/Member in MLM network"""
    __tablename__ = 'partners'
    
    id = Column(Integer, primary_key=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    phone = Column(String(50))
    telegram_id = Column(String(50), unique=True)
    
    upline_id = Column(Integer, ForeignKey('partners.id'), nullable=True)
    status = Column(SQLEnum(PartnerStatus), default=PartnerStatus.ACTIVE)
    commission_level = Column(Integer, default=1)
    
    registration_date = Column(DateTime, default=datetime.now)
    last_activity = Column(DateTime, default=datetime.now)
    
    total_sales = Column(Float, default=0.0)
    total_commissions = Column(Float, default=0.0)
    monthly_target = Column(Float, default=0.0)
    
    address = Column(Text)
    city = Column(String(100))
    country = Column(String(100))
    postal_code = Column(String(20))
    
    upline = relationship('Partner', remote_side=[id], backref='downline')
    orders = relationship('Order', back_populates='partner')
    commissions_earned = relationship('Commission', foreign_keys='Commission.partner_id', back_populates='partner')

class Product(Base):
    """NANOREM Product"""
    __tablename__ = 'products'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    sku = Column(String(100), unique=True)
    category = Column(String(100))
    
    price = Column(Float, nullable=False)
    partner_price = Column(Float)
    cost = Column(Float)
    
    stock_quantity = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    order_items = relationship('OrderItem', back_populates='product')

class Order(Base):
    """Customer/Partner Order"""
    __tablename__ = 'orders'
    
    id = Column(Integer, primary_key=True)
    order_number = Column(String(50), unique=True, nullable=False)
    
    partner_id = Column(Integer, ForeignKey('partners.id'), nullable=False)
    customer_name = Column(String(255))
    customer_email = Column(String(255))
    customer_phone = Column(String(50))
    
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING)
    
    subtotal = Column(Float, nullable=False)
    tax = Column(Float, default=0.0)
    shipping = Column(Float, default=0.0)
    total = Column(Float, nullable=False)
    
    payment_method = Column(String(50))
    payment_status = Column(String(50))
    
    shipping_address = Column(Text)
    shipping_city = Column(String(100))
    shipping_country = Column(String(100))
    shipping_postal_code = Column(String(20))
    
    notes = Column(Text)
    
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    shipped_at = Column(DateTime)
    delivered_at = Column(DateTime)
    
    partner = relationship('Partner', back_populates='orders')
    items = relationship('OrderItem', back_populates='order', cascade='all, delete-orphan')
    commissions = relationship('Commission', back_populates='order')

class OrderItem(Base):
    """Individual item in order"""
    __tablename__ = 'order_items'
    
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=False)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    subtotal = Column(Float, nullable=False)
    
    order = relationship('Order', back_populates='items')
    product = relationship('Product', back_populates='order_items')

class Commission(Base):
    """Commission record for partners"""
    __tablename__ = 'commissions'
    
    id = Column(Integer, primary_key=True)
    partner_id = Column(Integer, ForeignKey('partners.id'), nullable=False)
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=False)
    source_partner_id = Column(Integer, ForeignKey('partners.id'))
    
    level = Column(Integer, nullable=False)
    rate = Column(Float, nullable=False)
    base_amount = Column(Float, nullable=False)
    commission_amount = Column(Float, nullable=False)
    
    status = Column(SQLEnum(CommissionStatus), default=CommissionStatus.PENDING)
    
    created_at = Column(DateTime, default=datetime.now)
    approved_at = Column(DateTime)
    paid_at = Column(DateTime)
    
    notes = Column(Text)
    
    partner = relationship('Partner', foreign_keys=[partner_id], back_populates='commissions_earned')
    order = relationship('Order', back_populates='commissions')
    source_partner = relationship('Partner', foreign_keys=[source_partner_id])
