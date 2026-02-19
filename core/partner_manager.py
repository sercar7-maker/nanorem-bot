"""Partner Management Module for NANOREM MLM System

Handles partner profiles, registration, status tracking, and integration 
with the MLM NetworkManager and CommissionCalculator.
"""
from typing import Optional, List, Dict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class PartnerStatus(Enum):
    """Partner status enumeration."""
    ACTIVE = "active"        # Paid (3,000 monthly or 10,000 annual)
    INACTIVE = "inactive"    # Unpaid (loss of percentage, leads to compression)
    SUSPENDED = "suspended"  # Manual hold
    TERMINATED = "terminated" # Deleted after 1 year of inactivity


@dataclass
class Partner:
    """Partner data model."""
    partner_id: int
    first_name: str
    last_name: str
    email: str
    phone: str
    upline_id: Optional[int] = None
    status: PartnerStatus = PartnerStatus.ACTIVE
    registration_date: datetime = field(default_factory=datetime.now)
    last_activity_date: datetime = field(default_factory=datetime.now)
    
    # Financial metrics (accumulated)
    total_procurement: float = 0.0   # Total purchase volume
    total_commissions: float = 0.0   # Total earned commissions
    
    def get_full_name(self) -> str:
        """Get partner full name."""
        return f"{self.first_name} {self.last_name}"

    @property
    def is_active(self) -> bool:
        """Check if partner is active based on status."""
        return self.status == PartnerStatus.ACTIVE


class PartnerManager:
    """
    Manager for partner operations in NANOREM MLM system.
    
    Orchestrates:
    - Partner registration.
    - Status updates (Active/Inactive/Terminated).
    - Accumulation of sales and commission totals.
    """

    def __init__(self, network_manager=None):
        """
        Initialize partner manager.
        
        Args:
            network_manager: Optional instance of NetworkManager to keep
                             in sync with partner status changes.
        """
        self.partners: Dict[int, Partner] = {}
        self.network_manager = network_manager
        self.logger = logger

    # -----------------------------------------------------------------------
    # Registration & Lookup
    # -----------------------------------------------------------------------

    def register_partner(
        self,
        partner_id: int,
        first_name: str,
        last_name: str,
        email: str,
        phone: str,
        upline_id: Optional[int] = None
    ) -> Partner:
        """
        Register a new partner and add them to the network.
        """
        if partner_id in self.partners:
            self.logger.warning(f"Partner ID {partner_id} already registered.")
            return self.partners[partner_id]

        partner = Partner(
            partner_id=partner_id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            upline_id=upline_id
        )

        self.partners[partner_id] = partner
        
        # Sync with network manager
        if self.network_manager:
            self.network_manager.add_partner(partner_id, upline_id)

        self.logger.info(f"Partner {partner_id} registered successfully.")
        return partner

    def get_partner(self, partner_id: int) -> Optional[Partner]:
        """Lookup partner by ID."""
        return self.partners.get(partner_id)

    # -----------------------------------------------------------------------
    # Status & Activity
    # -----------------------------------------------------------------------

    def update_status(self, partner_id: int, new_status: PartnerStatus) -> bool:
        """
        Update partner status and sync with network (for compression).
        """
        partner = self.get_partner(partner_id)
        if not partner:
            return False

        old_status = partner.status
        partner.status = new_status
        
        self.logger.info(
            f"Partner {partner_id} status changed: {old_status} -> {new_status}"
        )

        # If partner becomes inactive/terminated, notify network manager 
        # to trigger structural compression if needed.
        if self.network_manager:
            if new_status in [PartnerStatus.INACTIVE, PartnerStatus.TERMINATED]:
                self.network_manager.deactivate_partner(partner_id)
            elif new_status == PartnerStatus.ACTIVE and old_status != PartnerStatus.ACTIVE:
                self.network_manager.reactivate_partner(partner_id)

        return True

    def record_activity(self, partner_id: int) -> bool:
        """Update last activity timestamp."""
        partner = self.get_partner(partner_id)
        if partner:
            partner.last_activity_date = datetime.now()
            return True
        return False

    # -----------------------------------------------------------------------
    # Financial Updates
    # -----------------------------------------------------------------------

    def add_procurement_volume(self, partner_id: int, amount: float) -> bool:
        """Add to partner's total purchase volume."""
        partner = self.get_partner(partner_id)
        if not partner:
            return False
        partner.total_procurement += amount
        return True

    def add_commission_earned(self, partner_id: int, amount: float) -> bool:
        """Add to partner's total earned commissions."""
        partner = self.get_partner(partner_id)
Refactor partner_manager.py: Sync with NetworkManager, updated statuses, financial metrics            return False
        partner.total_commissions += amount
        return True

    # -----------------------------------------------------------------------
    # Queries
    # -----------------------------------------------------------------------

    def get_active_partners(self) -> List[Partner]:
        """Return list of all partners with ACTIVE status."""
        return [p for p in self.partners.values() if p.is_active]

    def get_partner_summary(self, partner_id: int) -> Dict:
        """Return a summary dict for the partner."""
        p = self.get_partner(partner_id)
        if not p:
            return {}
        
        return {
            "id": p.partner_id,
            "name": p.get_full_name(),
            "status": p.status.value,
            "upline": p.upline_id,
            "total_procurement": p.total_procurement,
            "total_commissions": p.total_commissions,
            "registered": p.registration_date.isoformat(),
            "last_activity": p.last_activity_date.isoformat()
        }
