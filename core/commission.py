"""Commission Calculator Module for NANOREM MLM System

Handles all commission calculations for the multi-level marketing structure.
Supports multiple levels, bonuses, and various commission types.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


@dataclass
class CommissionRecord:
    """Record of a single commission transaction"""
    commission_id: int
    partner_id: int
    source_partner_id: int  # Partner who made the sale
    level: int
    amount: Decimal
    base_amount: Decimal  # Original sale amount
    rate: Decimal  # Commission rate applied
    timestamp: datetime = field(default_factory=datetime.now)
    status: str = 'pending'  # pending, approved, paid
    notes: Optional[str] = None


class CommissionCalculator:
    """
    Commission Calculator for MLM Network
    
    Calculates commissions based on sales in the partner network.
    Supports multiple levels with configurable rates.
    """
    
    def __init__(self, commission_rates: Dict[str, float]):
        """
        Initialize commission calculator.
        
        Args:
            commission_rates: Dictionary mapping level to commission rate
                Example: {'level_1': 15.0, 'level_2': 8.0, 'level_3': 5.0}
        """
        self.commission_rates = commission_rates
        self.commissions: List[CommissionRecord] = []
        self._next_commission_id = 1
        self.logger = logger
    
    def calculate_sale_commissions(
        self,
        sale_amount: float,
        selling_partner_id: int,
        upline_chain: List[int]
    ) -> List[CommissionRecord]:
        """
        Calculate commissions for a sale across the upline.
        
        Args:
            sale_amount: Total sale amount
            selling_partner_id: ID of partner who made the sale
            upline_chain: List of upline partner IDs [direct_upline, level_2, level_3, ...]
        
        Returns:
            List of CommissionRecord objects for each level
        """
        calculated_commissions = []
        base_amount = Decimal(str(sale_amount))
        
        self.logger.info(
            f"Calculating commissions for sale: {sale_amount} by partner {selling_partner_id}"
        )
        
        for level_index, upline_partner_id in enumerate(upline_chain, start=1):
            level_key = f"level_{level_index}"
            
            if level_key not in self.commission_rates:
                self.logger.warning(f"No commission rate for {level_key}")
                continue
            
            rate = Decimal(str(self.commission_rates[level_key])) / Decimal('100')
            commission_amount = base_amount * rate
            
            commission = CommissionRecord(
                commission_id=self._next_commission_id,
                partner_id=upline_partner_id,
                source_partner_id=selling_partner_id,
                level=level_index,
                amount=commission_amount,
                base_amount=base_amount,
                rate=rate * Decimal('100'),
                status='pending'
            )
            
            calculated_commissions.append(commission)
            self.commissions.append(commission)
            self._next_commission_id += 1
            
            self.logger.info(
                f"Level {level_index}: Partner {upline_partner_id} earns "
                f"{commission_amount:.2f} ({rate*100:.1f}%)"
            )
        
        return calculated_commissions
    
    def calculate_team_bonus(
        self,
        partner_id: int,
        team_sales: float,
        bonus_rate: float
    ) -> Decimal:
        """
        Calculate team bonus based on total team sales.
        
        Args:
            partner_id: Partner ID
            team_sales: Total sales from team
            bonus_rate: Bonus rate percentage
        
        Returns:
            Bonus amount
        """
        bonus_amount = Decimal(str(team_sales)) * Decimal(str(bonus_rate)) / Decimal('100')
        
        self.logger.info(
            f"Team bonus for partner {partner_id}: {bonus_amount:.2f} "
            f"(team sales: {team_sales:.2f}, rate: {bonus_rate}%)"
        )
        
        return bonus_amount
    
    def calculate_performance_bonus(
        self,
        partner_id: int,
        monthly_sales: float,
        target: float,
        bonus_amount: float
    ) -> Decimal:
        """
        Calculate performance bonus if target is met.
        
        Args:
            partner_id: Partner ID
            monthly_sales: Partner's monthly sales
            target: Monthly sales target
            bonus_amount: Fixed bonus amount if target met
        
        Returns:
            Bonus amount (0 if target not met)
        """
        if monthly_sales >= target:
            bonus = Decimal(str(bonus_amount))
            self.logger.info(
                f"Performance bonus for partner {partner_id}: {bonus:.2f} "
                f"(sales: {monthly_sales:.2f} >= target: {target:.2f})"
            )
            return bonus
        else:
            self.logger.info(
                f"No performance bonus for partner {partner_id} "
                f"(sales: {monthly_sales:.2f} < target: {target:.2f})"
            )
            return Decimal('0')
    
    def get_total_commissions(
        self,
        partner_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        status: Optional[str] = None
    ) -> Decimal:
        """
        Get total commissions for a partner.
        
        Args:
            partner_id: Partner ID
            start_date: Filter by start date (optional)
            end_date: Filter by end date (optional)
            status: Filter by status (optional)
        
        Returns:
            Total commission amount
        """
        filtered_commissions = [
            c for c in self.commissions
            if c.partner_id == partner_id and
            (start_date is None or c.timestamp >= start_date) and
            (end_date is None or c.timestamp <= end_date) and
            (status is None or c.status == status)
        ]
        
        total = sum(c.amount for c in filtered_commissions)
        return total
    
    def get_commissions_by_level(
        self,
        partner_id: int,
        level: int
    ) -> List[CommissionRecord]:
        """
        Get all commissions for a partner at specific level.
        
        Args:
            partner_id: Partner ID
            level: Commission level (1, 2, 3, etc.)
        
        Returns:
            List of commission records
        """
        return [
            c for c in self.commissions
            if c.partner_id == partner_id and c.level == level
        ]
    
    def approve_commission(self, commission_id: int) -> bool:
        """
        Approve a commission for payment.
        
        Args:
            commission_id: Commission ID to approve
        
        Returns:
            True if approved, False if not found
        """
        for commission in self.commissions:
            if commission.commission_id == commission_id:
                commission.status = 'approved'
                self.logger.info(f"Commission {commission_id} approved")
                return True
        
        self.logger.warning(f"Commission {commission_id} not found")
        return False
    
    def mark_as_paid(self, commission_id: int) -> bool:
        """
        Mark commission as paid.
        
        Args:
            commission_id: Commission ID
        
        Returns:
            True if marked, False if not found
        """
        for commission in self.commissions:
            if commission.commission_id == commission_id:
                commission.status = 'paid'
                self.logger.info(f"Commission {commission_id} marked as paid")
                return True
        
        self.logger.warning(f"Commission {commission_id} not found")
        return False
    
    def get_commission_summary(
        self,
        partner_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict:
        """
        Get commission summary for partner.
        
        Args:
            partner_id: Partner ID
            start_date: Start date for summary
            end_date: End date for summary
        
        Returns:
            Dictionary with commission summary
        """
        filtered = [
            c for c in self.commissions
            if c.partner_id == partner_id and
            (start_date is None or c.timestamp >= start_date) and
            (end_date is None or c.timestamp <= end_date)
        ]
        
        total = sum(c.amount for c in filtered)
        pending = sum(c.amount for c in filtered if c.status == 'pending')
        approved = sum(c.amount for c in filtered if c.status == 'approved')
        paid = sum(c.amount for c in filtered if c.status == 'paid')
        
        by_level = {}
        for level in range(1, 5):  # Up to level 4
            level_comms = [c for c in filtered if c.level == level]
            if level_comms:
                by_level[f"level_{level}"] = {
                    'count': len(level_comms),
                    'total': sum(c.amount for c in level_comms)
                }
        
        return {
            'partner_id': partner_id,
            'total_commissions': float(total),
            'pending': float(pending),
            'approved': float(approved),
            'paid': float(paid),
            'by_level': by_level,
            'commission_count': len(filtered)
        }
