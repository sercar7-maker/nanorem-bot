"""Cloud Cash Register Integration Module.
Handles receipt processing and synchronization with the MLM system.
"""
import logging
from datetime import datetime
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from database.db import SessionLocal
from database.models import Purchase, Partner, Commission, OrderStatus, CommissionStatus
from core.commission import CommissionCalculator
from telegram.notifications import notify_commission

logger = logging.getLogger(__name__)

class CashRegisterIntegration:
    """Orchestrator for Cash Register events and MLM payouts."""

    def __init__(self, session: Session = None):
        self.session = session
        self.calculator = CommissionCalculator()

    async def process_purchase(self, data: Dict[str, Any]) -> bool:
        """
        Register a purchase and trigger MLM commissions.
        Expects keys: partner_id (or telegram_id), amount, order_id
        """
        # Allow either passed session or new session
        session = self.session if self.session else SessionLocal()
        
        try:
            partner_id = data.get('partner_id')
            telegram_id = data.get('telegram_id')
            amount = float(data.get('amount', 0))
            order_id = data.get('order_id')

            # 1. Resolve partner
            if partner_id:
                partner = session.query(Partner).get(partner_id)
            else:
                partner = session.query(Partner).filter(Partner.telegram_id == telegram_id).first()

            if not partner:
                logger.error(f"Partner not found for purchase data: {data}")
                return False

            # 2. Save Purchase
            purchase = Purchase(
                purchase_number=order_id or f"PUR-{int(datetime.utcnow().timestamp())}",
                partner_id=partner.id,
                amount=amount,
                status=OrderStatus.PAID,
                paid_at=datetime.utcnow(),
                ext_ref=order_id
            )
            session.add(purchase)
            session.flush()

            # 3. Build upline chain
            upline_chain = self._get_upline_chain(session, partner.id)

            # 4. Calculate Commissions (core logic)
            calculated = self.calculator.calculate_purchase_commissions(
                purchase_amount=amount,
                buying_partner_id=partner.id,
                upline_chain=upline_chain
            )

            # 5. Save and Notify
            notifications = []
            buyer_name = partner.username or f"ID:{partner.telegram_id}"
            
            for c in calculated:
                db_comm = Commission(
                    partner_id=c.partner_id,
                    purchase_id=purchase.id,
                    source_partner_id=partner.id,
                    level=c.level,
                    rate=c.rate,
                    base_amount=c.base_amount,
                    amount=c.amount,
                    status=CommissionStatus.PENDING,
                    is_compressed=c.compressed,
                    notes=c.notes
                )
                session.add(db_comm)
                
                # Fetch telegram_id for notification
                beneficiary = session.query(Partner).get(c.partner_id)
                if beneficiary and beneficiary.telegram_id:
                    notifications.append(
                        notify_commission(
                            beneficiary.telegram_id, 
                            c.amount, 
                            c.level, 
                            buyer_name
                        )
                    )

            if not self.session: # Commit only if we created the session
                session.commit()
                
            # Trigger notifications asynchronously
            import asyncio
            if notifications:
                asyncio.create_task(asyncio.gather(*notifications))

            logger.info(f"Processed purchase for {buyer_name}: {amount} rub. Commissions: {len(calculated)}")
            return True

        except Exception as e:
            if not self.session: session.rollback()
            logger.error(f"Failed to process purchase: {e}")
            return False
        finally:
            if not self.session: session.close()

    def _get_upline_chain(self, session: Session, start_id: int) -> List[tuple]:
        """Build (partner_id, is_active) chain for calculator."""
        chain = []
        curr = session.query(Partner).get(start_id)
        
        # Max 5 levels of payouts usually, but let's walk enough for compression
        for _ in range(10):
            if not curr or not curr.upline_id: break
            
            # Find upline partner by telegram_id (upline_id is telegram_id in current models)
            upline = session.query(Partner).filter(Partner.telegram_id == curr.upline_id).first()
            if not upline: break
            
            chain.append((upline.id, upline.is_active))
            curr = upline
            
        return chain
