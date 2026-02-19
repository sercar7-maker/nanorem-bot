"""Commission Calculator Module for NANOREM MLM System

Handles all commission calculations for the 5-level marketing structure.
Commission base: total purchase (procurement) amount.
Rates: Level 1 - 20%, Level 2 - 10%, Levels 3-4-5 - 5% each.
Compression: if a partner in the chain is inactive, their level is skipped
and the commission is passed one level up to the next active partner.
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Commission rates for 5-level NANOREM MLM structure
# Base: total procurement (purchase) amount
# ---------------------------------------------------------------------------
DEFAULT_COMMISSION_RATES: Dict[int, Decimal] = {
    1: Decimal('20.0'),  # Direct upline
    2: Decimal('10.0'),  # 2nd level
    3: Decimal('5.0'),   # 3rd level
    4: Decimal('5.0'),   # 4th level
    5: Decimal('5.0'),   # 5th level
}

MAX_LEVELS = 5


@dataclass
class CommissionRecord:
    """Record of a single commission transaction"""
    commission_id: int
    partner_id: int
    source_partner_id: int  # Partner who made the purchase
    level: int              # Actual structural level (1-5)
    amount: Decimal         # Commission amount
    base_amount: Decimal    # Total procurement amount (base for calculation)
    rate: Decimal           # Commission rate applied (%)
    timestamp: datetime = field(default_factory=datetime.now)
    status: str = 'pending'  # pending, approved, paid
    compressed: bool = False  # True if this record was created via compression
    notes: Optional[str] = None


class CommissionCalculator:
    """
    Commission Calculator for NANOREM 5-level MLM Network.

    Rules:
    - Base for calculation: total procurement (purchase) amount.
    - Rates by structural level: 20% / 10% / 5% / 5% / 5%.
    - Number of branches is unlimited.
    - Compression: if a partner in the upline chain is inactive,
      their commission is NOT burned. Instead it is passed to the
      next active partner one level up (upward compression by 1 step).
    - Maximum depth: 5 levels.
    """

    def __init__(
        self,
        commission_rates: Optional[Dict[int, Decimal]] = None
    ):
        """
        Initialize commission calculator.

        Args:
            commission_rates: Dict mapping structural level (int) to rate (Decimal %).
                              Defaults to NANOREM standard rates.
        """
        self.commission_rates: Dict[int, Decimal] = (
            commission_rates if commission_rates is not None
            else DEFAULT_COMMISSION_RATES
        )
        self.commissions: List[CommissionRecord] = []
        self._next_commission_id = 1
        self.logger = logger

    # -----------------------------------------------------------------------
    # Core method
    # -----------------------------------------------------------------------

    def calculate_purchase_commissions(
        self,
        purchase_amount: float,
        buying_partner_id: int,
        upline_chain: List[Tuple[int, bool]]
    ) -> List[CommissionRecord]:
        """
        Calculate commissions for a procurement (purchase) across the upline.

        Args:
            purchase_amount:   Total procurement amount (base for all calculations).
            buying_partner_id: ID of the partner who made the purchase.
            upline_chain:      Ordered list of (partner_id, is_active) tuples,
                               starting from direct upline (level 1) going up.
                               Length can exceed MAX_LEVELS; only first MAX_LEVELS
                               structural slots are filled.

        Returns:
            List of CommissionRecord for each paid-out commission.

        Compression logic:
            - We iterate through upline_chain filling structural slots 1..5.
            - If a partner at the current slot is inactive, we skip them
              (their slot is consumed but no commission is issued to them).
              The commission for that slot is transferred to the next active
              partner encountered, who receives it at the SAME structural
              level (upward compression by one link).
            - If no active partner is found for a slot before reaching the
              end of the chain or MAX_LEVELS, that commission is not issued.
        """
        calculated: List[CommissionRecord] = []
        base = Decimal(str(purchase_amount))

        self.logger.info(
            f"Purchase commissions: amount={purchase_amount}, "
            f"buyer={buying_partner_id}"
        )

        structural_level = 1  # Current MLM level slot being filled (1-5)
        chain_index = 0       # Current position in upline_chain

        while structural_level <= MAX_LEVELS and chain_index < len(upline_chain):
            partner_id, is_active = upline_chain[chain_index]
            chain_index += 1

            if not is_active:
                # Partner is inactive: compress upward.
                # The structural slot is kept; we look for the next active
                # partner in the chain to receive this level's commission.
                self.logger.info(
                    f"Level {structural_level}: partner {partner_id} is inactive "
                    f"— compressing upward."
                )
                # Find next active partner without advancing structural level
                found = False
                while chain_index < len(upline_chain):
                    next_id, next_active = upline_chain[chain_index]
                    chain_index += 1
                    if next_active:
                        record = self._make_record(
                            base=base,
                            partner_id=next_id,
                            source_id=buying_partner_id,
                            level=structural_level,
                            compressed=True
                        )
                        if record:
                            calculated.append(record)
                            self.commissions.append(record)
                        found = True
                        break
                if not found:
                    self.logger.warning(
                        f"Level {structural_level}: no active upline found "
                        f"after compression — commission not issued."
                    )
            else:
                # Active partner — standard commission
                record = self._make_record(
                    base=base,
                    partner_id=partner_id,
                    source_id=buying_partner_id,
                    level=structural_level,
                    compressed=False
                )
                if record:
                    calculated.append(record)
                    self.commissions.append(record)

            structural_level += 1

        return calculated

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _make_record(
        self,
        base: Decimal,
        partner_id: int,
        source_id: int,
        level: int,
        compressed: bool
    ) -> Optional[CommissionRecord]:
        """Create a CommissionRecord for a given structural level."""
        if level not in self.commission_rates:
            self.logger.warning(f"No commission rate for level {level}")
            return None

        rate = self.commission_rates[level]
        amount = base * rate / Decimal('100')

        record = CommissionRecord(
            commission_id=self._next_commission_id,
            partner_id=partner_id,
            source_partner_id=source_id,
            level=level,
            amount=amount,
            base_amount=base,
            rate=rate,
            compressed=compressed,
            notes="compressed upward" if compressed else None
        )
        self._next_commission_id += 1

        self.logger.info(
            f"Level {level}: partner {partner_id} earns "
            f"{amount:.2f} ({rate}%)"
            + (" [compressed]" if compressed else "")
        )
        return record

    # -----------------------------------------------------------------------
    # Query helpers
    # -----------------------------------------------------------------------

    def get_total_commissions(
        self,
        partner_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        status: Optional[str] = None
    ) -> Decimal:
        """
        Get total commissions earned by a partner.

        Args:
            partner_id: Partner ID.
            start_date: Filter from date (inclusive).
            end_date:   Filter to date (inclusive).
            status:     Filter by status ('pending', 'approved', 'paid').

        Returns:
            Total commission amount as Decimal.
        """
        filtered = [
            c for c in self.commissions
            if c.partner_id == partner_id
            and (start_date is None or c.timestamp >= start_date)
            and (end_date is None or c.timestamp <= end_date)
            and (status is None or c.status == status)
        ]
        return sum((c.amount for c in filtered), Decimal('0'))

    def get_commissions_by_level(
        self,
        partner_id: int,
        level: int
    ) -> List[CommissionRecord]:
        """
        Get all commission records for a partner at a specific structural level.

        Args:
            partner_id: Partner ID.
            level:      Structural level (1-5).

        Returns:
            List of CommissionRecord.
        """
        return [
            c for c in self.commissions
            if c.partner_id == partner_id and c.level == level
        ]

    def get_commission_summary(
        self,
        partner_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict:
        """
        Get a full commission summary for a partner.

        Returns:
            Dict with totals by status and by level.
        """
        filtered = [
            c for c in self.commissions
            if c.partner_id == partner_id
            and (start_date is None or c.timestamp >= start_date)
            and (end_date is None or c.timestamp <= end_date)
        ]

        total = sum((c.amount for c in filtered), Decimal('0'))
        pending = sum((c.amount for c in filtered if c.status == 'pending'), Decimal('0'))
        approved = sum((c.amount for c in filtered if c.status == 'approved'), Decimal('0'))
        paid = sum((c.amount for c in filtered if c.status == 'paid'), Decimal('0'))

        by_level: Dict[str, dict] = {}
        for lvl in range(1, MAX_LEVELS + 1):
            lvl_records = [c for c in filtered if c.level == lvl]
            if lvl_records:
                by_level[f"level_{lvl}"] = {
                    'count': len(lvl_records),
                    'total': float(sum((c.amount for c in lvl_records), Decimal('0'))),
                    'rate': float(self.commission_rates.get(lvl, Decimal('0')))
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

    # -----------------------------------------------------------------------
    # Status management
    # -----------------------------------------------------------------------

    def approve_commission(self, commission_id: int) -> bool:
        """Approve a commission for payment."""
        for c in self.commissions:
            if c.commission_id == commission_id:
                c.status = 'approved'
                self.logger.info(f"Commission {commission_id} approved")
                return True
        self.logger.warning(f"Commission {commission_id} not found")
        return False

    def mark_as_paid(self, commission_id: int) -> bool:
        """Mark commission as paid."""
        for c in self.commissions:
            if c.commission_id == commission_id:
                c.status = 'paid'
                self.logger.info(f"Commission {commission_id} marked as paid")
                return True
        self.logger.warning(f"Commission {commission_id} not found")
        return False
