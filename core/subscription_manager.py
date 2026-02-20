import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

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

    @staticmethod
    def activate_status(
        telegram_id: str,
        duration_days: int = STATUS_ACTIVE_DURATION_DAYS,
        session: Optional[Session] = None,
    ) -> bool:
        """
        Activate ACTIVE status for the partner with expiration date.
        Returns True if activation was successful.
        """
        close_session = False
        if session is None:
            session = get_session()
            close_session = True

        try:
            partner = session.query(Partner).filter(
                Partner.telegram_id == str(telegram_id)
            ).first()
            if not partner:
                logger.warning(f"Partner {telegram_id} not found for status activation")
                return False

            partner.status = PartnerStatus.ACTIVE
            partner.subscription_end_date = datetime.utcnow() + timedelta(days=duration_days)

            session.commit()
            logger.info(
                f"Partner {telegram_id} activated, "
                f"expires at {partner.subscription_end_date}"
            )
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Error activating status for partner {telegram_id}: {e}")
            return False
        finally:
            if close_session:
                session.close()

    @staticmethod
    def check_and_expire_statuses() -> int:
        """
        Check all partners and expire (burn) statuses that have passed their end date.
        Returns the count of expired partners.
        """
        session = get_session()
        expired_count = 0

        try:
            now = datetime.utcnow()
            # Find partners with expired subscriptions who still have ACTIVE status
            expired_partners = (
                session.query(Partner)
                .filter(
                    Partner.subscription_end_date.isnot(None),
                    Partner.subscription_end_date < now,
                    Partner.status == PartnerStatus.ACTIVE,
                )
                .all()
            )

            for partner in expired_partners:
                old_status = partner.status
                partner.status = PartnerStatus.INACTIVE
                partner.subscription_end_date = None
                expired_count += 1
                logger.info(
                    f"Partner {partner.telegram_id} status expired: "
                    f"{old_status.value} -> INACTIVE"
                )

            if expired_count > 0:
                session.commit()
                logger.info(f"Expired {expired_count} partner statuses")

            return expired_count
        except Exception as e:
            session.rollback()
            logger.error(f"Error checking/expiring statuses: {e}")
            return 0
        finally:
            session.close()

    @staticmethod
    def get_days_until_expiry(telegram_id: str) -> Optional[int]:
        """
        Get the number of days until a partner's status expires.
        Returns None if partner has no expiry date.
        Returns negative number if already expired.
        """
        session = get_session()
        try:
            partner = session.query(Partner).filter(
                Partner.telegram_id == str(telegram_id)
            ).first()
            if not partner or not partner.subscription_end_date:
                return None
            delta = partner.subscription_end_date - datetime.utcnow()
            return delta.days
        except Exception as e:
            logger.error(f"Error getting expiry days for partner {telegram_id}: {e}")
            return None
        finally:
            session.close()

    @staticmethod
    def is_status_active(telegram_id: str) -> bool:
        """
        Check if partner's current status is still active (not expired).
        """
        session = get_session()
        try:
            partner = session.query(Partner).filter(
                Partner.telegram_id == str(telegram_id)
            ).first()
            if not partner:
                return False
            if partner.status != PartnerStatus.ACTIVE:
                return False
            if partner.subscription_end_date is None:
                return True  # No expiry = permanent active
            return partner.subscription_end_date > datetime.utcnow()
        except Exception as e:
            logger.error(f"Error checking active status for partner {telegram_id}: {e}")
            return False
        finally:
            session.close()

    @staticmethod
    def renew_status(telegram_id: str, additional_days: int = 30) -> bool:
        """
        Extend partner's current ACTIVE status by additional_days.
        """
        session = get_session()
        try:
            partner = session.query(Partner).filter(
                Partner.telegram_id == str(telegram_id)
            ).first()
            if not partner:
                return False

            if (
                partner.subscription_end_date
                and partner.subscription_end_date > datetime.utcnow()
            ):
                # Extend from current end date
                partner.subscription_end_date += timedelta(days=additional_days)
            else:
                # Start fresh from now
                partner.subscription_end_date = datetime.utcnow() + timedelta(
                    days=additional_days
                )

            partner.status = PartnerStatus.ACTIVE
            session.commit()
            logger.info(
                f"Partner {telegram_id} status renewed by {additional_days} days, "
                f"new expiry: {partner.subscription_end_date}"
            )
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Error renewing status for partner {telegram_id}: {e}")
            return False
        finally:
            session.close()


# Singleton instance
subscription_manager = SubscriptionManager()
