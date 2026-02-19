"""Cloud Cash Register Integration Module.

Handles receipt processing and synchronization with the MLM system.
Processes material procurement (purchase) to distribute commissions.
"""
import logging
import asyncio
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from database.db import db
from database.models import Purchase, Partner, Commission, OrderStatus, CommissionStatus, PartnerStatus
from core.commission import CommissionCalculator

logger = logging.getLogger(__name__)


class ReceiptStatus(Enum):
    """Receipt status enumeration."""
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass
class Receipt:
    """Receipt data model from cash register."""
    receipt_id: str
    partner_id: int
    amount: float
    items: List[Dict[str, Any]]
    status: ReceiptStatus = ReceiptStatus.PENDING
    timestamp: datetime = None
    external_receipt_id: Optional[str] = None
    payment_method: str = "cash"
    notes: Optional[str] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class CashRegisterIntegration:
    """
    Orchestrator for Cash Register events and MLM payouts.
    """

    def __init__(self):
        self.calculator = CommissionCalculator()
        self.logger = logger

    async def process_purchase(self, partner_id: int, amount: float, ext_ref: str = None) -> bool:
        """
        Main entry point: Register a purchase and trigger MLM commissions.
        
        Args:
            partner_id: ID of the partner who bought materials.
            amount:     Total procurement amount.
            ext_ref:    External reference (e.g., store order ID).
            
        Returns:
            True if processed and commissions saved, False otherwise.
        """
        session = db.get_session()
        try:
            # 1. Verify partner exists
            partner = session.query(Partner).get(partner_id)
            if not partner:
                self.logger.error(f"Partner {partner_id} not found for purchase.")
                return False

            # 2. Create and save Purchase record
            purchase_no = f"PUR-{int(datetime.utcnow().timestamp())}-{partner_id}"
            new_purchase = Purchase(
                purchase_number=purchase_no,
                partner_id=partner_id,
                amount=amount,
                status=OrderStatus.PAID,
                paid_at=datetime.utcnow(),
                ext_ref=ext_ref
            )
            session.add(new_purchase)
            session.flush() # Ensure ID is generated for commission linking

            # 3. Build upline chain for commission calculation
            upline_chain = self._get_upline_chain(session, partner_id)

            # 4. Calculate commissions (using core logic: 20/10/5/5/5 with compression)
            calculated_comms = self.calculator.calculate_purchase_commissions(
                purchase_amount=amount,
                buying_partner_id=partner_id,
                upline_chain=upline_chain
            )

            # 5. Save results and update totals
            partner.total_procurement += amount
            
            for comm in calculated_comms:
                db_comm = Commission(
                    partner_id=comm.partner_id,
                    purchase_id=new_purchase.id,
                    source_partner_id=partner_id,
                    level=comm.level,
                    rate=float(comm.rate),
                    base_amount=float(comm.base_amount),
                    amount=float(comm.amount),
                    status=CommissionStatus.PENDING,
                    is_compressed=comm.compressed,
                    notes=comm.notes
                )
                session.add(db_comm)
                
                # Increment beneficiary's total accumulated commissions
                beneficiary = session.query(Partner).get(comm.partner_id)
                if beneficiary:
                    beneficiary.total_commissions += float(comm.amount)

            session.commit()
            self.logger.info(
                f"Successfully processed purchase {purchase_no} for partner {partner_id}. "
                f"Distributed {len(calculated_comms)} commissions."
            )
            return True

        except Exception as e:
            session.rollback()
            self.logger.error(f"Failed to process purchase for partner {partner_id}: {e}")
            return False
        finally:
            db.remove_session()

    def _get_upline_chain(self, session, start_partner_id: int) -> List[tuple]:
        """
        Walk up the partner hierarchy to build a chain for the CommissionCalculator.
        
        Returns:
            List of (partner_id, is_active) starting from direct upline.
        """
        chain = []
        curr_id = start_partner_id
        
        # Limit depth for safety (payouts are max 5 levels anyway)
        for _ in range(10):
            partner = session.query(Partner).get(curr_id)
            if not partner or not partner.upline_id:
                break
            
            upline = session.query(Partner).get(partner.upline_id)
            if not upline:
                break
                
            # Activity check: must have ACTIVE status
            is_active = (upline.status == PartnerStatus.ACTIVE)
            chain.append((upline.id, is_active))
            curr_id = upline.id
            
        return chain

    async def handle_webhook(self, data: Dict[str, Any]) -> bool:
        """
        Process incoming payment/receipt webhook from external cloud register.
        """
        # Standardize external payload
        p_id = data.get('partner_id')
        amt = data.get('total')
        ref = data.get('order_id')
        
        if p_id and amt:
            return await self.process_purchase(p_id, amt, ref)
        
        self.logger.warning(f"Invalid webhook data received: {data}")
        return False
