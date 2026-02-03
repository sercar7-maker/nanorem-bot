"""Partner Management Module for NANOREM MLM System"""

from typing import Optional, List, Dict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class PartnerStatus(Enum):
    """Partner status enumeration"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


@dataclass
class Partner:
    """Partner data model"""
    partner_id: int
    first_name: str
    last_name: str
    email: str
    phone: str
    upline_id: Optional[int] = None
    status: PartnerStatus = PartnerStatus.ACTIVE
    commission_level: int = 1
    registration_date: datetime = field(default_factory=datetime.now)
    total_sales: float = 0.0
    total_commissions: float = 0.0
    monthly_target: float = 0.0
    
    def get_full_name(self) -> str:
        """Get partner full name"""
        return f"{self.first_name} {self.last_name}"
    
    def is_active(self) -> bool:
        """Check if partner is active"""
        return self.status == PartnerStatus.ACTIVE


class PartnerManager:
    """Manager for partner operations in MLM system"""
    
    def __init__(self):
        self.partners: Dict[int, Partner] = {}
        self._next_id = 1
    
    def register_partner(
        self,
        first_name: str,
        last_name: str,
        email: str,
        phone: str,
        upline_id: Optional[int] = None
    ) -> Partner:
        """
        Register a new partner in the MLM system.
        
        Args:
            first_name: Partner's first name
            last_name: Partner's last name
            email: Partner's email address
            phone: Partner's phone number
            upline_id: ID of the upline partner (sponsor)
        
        Returns:
            Partner: The newly created partner object
        """
        partner_id = self._next_id
        self._next_id += 1
        
        partner = Partner(
            partner_id=partner_id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            upline_id=upline_id
        )
        
        self.partners[partner_id] = partner
        return partner
    
    def get_partner(self, partner_id: int) -> Optional[Partner]:
        """
        Get partner by ID.
        
        Args:
            partner_id: Partner ID
        
        Returns:
            Partner or None if not found
        """
        return self.partners.get(partner_id)
    
    def get_downline(self, partner_id: int) -> List[Partner]:
        """
        Get all direct downline partners.
        
        Args:
            partner_id: Partner ID
        
        Returns:
            List of direct downline partners
        """
        return [p for p in self.partners.values() if p.upline_id == partner_id]
    
    def get_network_tree(self, partner_id: int, level: int = 0, max_levels: Optional[int] = None) -> Dict:
        """
        Get network structure (upline/downline tree).
        
        Args:
            partner_id: Partner ID
            level: Current level in tree
            max_levels: Maximum levels to retrieve (None for unlimited)
        
        Returns:
            Dictionary representing network tree
        """
        if max_levels and level >= max_levels:
            return {}
        
        partner = self.get_partner(partner_id)
        if not partner:
            return {}
        
        downline = self.get_downline(partner_id)
        
        return {
            'partner': partner,
            'downline': [
                self.get_network_tree(p.partner_id, level + 1, max_levels)
                for p in downline
            ]
        }
    
    def update_partner_status(self, partner_id: int, status: PartnerStatus) -> bool:
        """
        Update partner status.
        
        Args:
            partner_id: Partner ID
            status: New status
        
        Returns:
            True if successful, False if partner not found
        """
        partner = self.get_partner(partner_id)
        if not partner:
            return False
        
        partner.status = status
        return True
    
    def add_sales(self, partner_id: int, amount: float) -> bool:
        """
        Add sales to partner record.
        
        Args:
            partner_id: Partner ID
            amount: Sales amount
        
        Returns:
            True if successful, False if partner not found
        """
        partner = self.get_partner(partner_id)
        if not partner:
            return False
        
        partner.total_sales += amount
        return True
    
    def add_commission(self, partner_id: int, amount: float) -> bool:
        """
        Add commission to partner.
        
        Args:
            partner_id: Partner ID
            amount: Commission amount
        
        Returns:
            True if successful, False if partner not found
        """
        partner = self.get_partner(partner_id)
        if not partner:
            return False
        
        partner.total_commissions += amount
        return True
    
    def get_active_partners(self) -> List[Partner]:
        """
        Get list of all active partners.
        
        Returns:
            List of active partners
        """
        return [p for p in self.partners.values() if p.is_active()]
    
    def get_total_network_sales(self, partner_id: int) -> float:
        """
        Calculate total sales in the partner's entire network.
        
        Args:
            partner_id: Partner ID
        
        Returns:
            Total sales amount from network
        """
        partner = self.get_partner(partner_id)
        if not partner:
            return 0.0
        
        total = partner.total_sales
        
        for downline_partner in self.get_downline(partner_id):
            total += self.get_total_network_sales(downline_partner.partner_id)
        
        return total
