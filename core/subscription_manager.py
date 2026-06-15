"""Subscription manager for NANOREM MLM partner status tracking."""
import logging
from datetime import datetime, timedelta
from typing import Optional

from database.models import Partner, PartnerStatus
from database.db import get_session

logger = logging.getLogger(__name__)

# Duration of active status in days
STATUS_ACTIVE_DURATION_DAYS = 30


class SubscriptionManager:
    """
    Manages partner subscription statuses and automatic expiration (burning).
    Implements the 'Activation' feature - automatic status expiration (Сгорание статуса).
    """

    def activate_status(self, telegram_id: str, days: int = STATUS_ACTIVE_DURATION_DAYS) -> bool:
        """
        Activate partner status for the given number of days.
        Returns True if successful, False otherwise.
        """
        try:
            with get_session() as session:
                partner = session.query(Partner).filter(
                    Partner.telegram_id == str(telegram_id)
                ).first()

                if not partner:
                    logger.warning(f"[SubscriptionManager] Partner {telegram_id} not found")
                    return False

                partner.status = PartnerStatus.ACTIVE
                partner.subscription_end_date = datetime.utcnow() + timedelta(days=days)
                logger.info(
                    f"[SubscriptionManager] Activated status for {telegram_id} "
                    f"until {partner.subscription_end_date}"
                )
                return True
        except Exception as e:
            logger.error(f"[SubscriptionManager] Error activating status for {telegram_id}: {e}")
            return False

    def deactivate_status(self, telegram_id: str) -> bool:
        """
        Deactivate partner status (Сгорание статуса).
        Returns True if successful, False otherwise.
        """
        try:
            with get_session() as session:
                partner = session.query(Partner).filter(
                    Partner.telegram_id == str(telegram_id)
                ).first()

                if not partner:
                    return False

                partner.status = PartnerStatus.INACTIVE
                partner.subscription_end_date = None
                logger.info(f"[SubscriptionManager] Deactivated status for {telegram_id}")
                return True
        except Exception as e:
            logger.error(f"[SubscriptionManager] Error deactivating status for {telegram_id}: {e}")
            return False

    def check_and_expire_statuses(self) -> int:
        """
        Check all active partners and expire those whose subscription_end_date has passed.
        Returns the count of expired partners.
        """
        expired_count = 0
        try:
            with get_session() as session:
                now = datetime.utcnow()
                expired_partners = session.query(Partner).filter(
                    Partner.status == PartnerStatus.ACTIVE,
                    Partner.subscription_end_date != None,
                    Partner.subscription_end_date < now
                ).all()

                for partner in expired_partners:
                    partner.status = PartnerStatus.INACTIVE
                    expired_count += 1
                    logger.info(
                        f"[SubscriptionManager] Expired status for partner "
                        f"{partner.telegram_id} (end_date={partner.subscription_end_date})"
                    )
        except Exception as e:
            logger.error(f"[SubscriptionManager] Error checking expired statuses: {e}")

        return expired_count

    def get_days_until_expiry(self, telegram_id: str) -> Optional[int]:
        """
        Get number of days until subscription expires.
        Returns None if partner not found or not active.
        """
        try:
            with get_session() as session:
                partner = session.query(Partner).filter(
                    Partner.telegram_id == str(telegram_id)
                ).first()

                if not partner or partner.status != PartnerStatus.ACTIVE:
                    return None

                if not partner.subscription_end_date:
                    return None

                days_left = (partner.subscription_end_date - datetime.utcnow()).days
                return max(0, days_left)
        except Exception as e:
            logger.error(f"[SubscriptionManager] Error getting expiry for {telegram_id}: {e}")
            return None

    def is_active(self, telegram_id: str) -> bool:
        """
        Check if partner status is active.
        """
        try:
            with get_session() as session:
                partner = session.query(Partner).filter(
                    Partner.telegram_id == str(telegram_id)
                ).first()
                return partner is not None and partner.status == PartnerStatus.ACTIVE
        except Exception as e:
            logger.error(f"[SubscriptionManager] Error checking status for {telegram_id}: {e}")
            return False


# Singleton instance
subscription_manager = SubscriptionManager()
