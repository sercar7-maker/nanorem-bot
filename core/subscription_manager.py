import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from database.models import User, UserStatus
from database.db import get_session

logger = logging.getLogger(__name__)

# Длительность активного статуса в днях
STATUS_DURATION_DAYS = {
    UserStatus.PARTNER: 30,
    UserStatus.SENIOR_PARTNER: 30,
    UserStatus.LEADER: 30,
    UserStatus.SENIOR_LEADER: 30,
    UserStatus.DIRECTOR: 30,
    UserStatus.PRESIDENT: 30,
}


class SubscriptionManager:
    """
    Manages user subscription statuses and automatic expiration (burning).
    Implements the 'Activation' feature - automatic status expiration.
    """

    @staticmethod
    def activate_status(
        user_id: int,
        new_status: UserStatus,
        session: Optional[Session] = None,
        duration_days: Optional[int] = None,
    ) -> bool:
        """
        Activate a new status for the user with expiration date.
        Returns True if activation was successful.
        """
        close_session = False
        if session is None:
            session = get_session()
            close_session = True

        try:
            user = session.query(User).filter(User.telegram_id == user_id).first()
            if not user:
                logger.warning(f"User {user_id} not found for status activation")
                return False

            days = duration_days or STATUS_DURATION_DAYS.get(new_status, 30)
            user.status = new_status
            user.subscription_end_date = datetime.utcnow() + timedelta(days=days)
            user.is_active = True

            session.commit()
            logger.info(
                f"User {user_id} activated to status {new_status.value}, "
                f"expires at {user.subscription_end_date}"
            )
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Error activating status for user {user_id}: {e}")
            return False
        finally:
            if close_session:
                session.close()

    @staticmethod
    def check_and_expire_statuses() -> int:
        """
        Check all users and expire (burn) statuses that have passed their end date.
        Returns the count of expired users.
        """
        session = get_session()
        expired_count = 0

        try:
            now = datetime.utcnow()
            # Find users with expired subscriptions who still have active statuses
            expired_users = (
                session.query(User)
                .filter(
                    User.subscription_end_date.isnot(None),
                    User.subscription_end_date < now,
                    User.status != UserStatus.NEWCOMER,
                    User.is_active == True,
                )
                .all()
            )

            for user in expired_users:
                old_status = user.status
                user.status = UserStatus.NEWCOMER
                user.is_active = False
                user.subscription_end_date = None
                expired_count += 1
                logger.info(
                    f"User {user.telegram_id} status expired: "
                    f"{old_status.value} -> NEWCOMER"
                )

            if expired_count > 0:
                session.commit()
                logger.info(f"Expired {expired_count} user statuses")

            return expired_count
        except Exception as e:
            session.rollback()
            logger.error(f"Error checking/expiring statuses: {e}")
            return 0
        finally:
            session.close()

    @staticmethod
    def get_days_until_expiry(user_id: int) -> Optional[int]:
        """
        Get the number of days until a user's status expires.
        Returns None if user has no expiry date.
        Returns negative number if already expired.
        """
        session = get_session()
        try:
            user = session.query(User).filter(User.telegram_id == user_id).first()
            if not user or not user.subscription_end_date:
                return None
            delta = user.subscription_end_date - datetime.utcnow()
            return delta.days
        except Exception as e:
            logger.error(f"Error getting expiry days for user {user_id}: {e}")
            return None
        finally:
            session.close()

    @staticmethod
    def is_status_active(user_id: int) -> bool:
        """
        Check if user's current status is still active (not expired).
        """
        days = SubscriptionManager.get_days_until_expiry(user_id)
        if days is None:
            return True  # No expiry = permanent (e.g. NEWCOMER)
        return days >= 0

    @staticmethod
    def renew_status(user_id: int, additional_days: int = 30) -> bool:
        """
        Extend user's current status by additional_days.
        """
        session = get_session()
        try:
            user = session.query(User).filter(User.telegram_id == user_id).first()
            if not user:
                return False

            if user.subscription_end_date and user.subscription_end_date > datetime.utcnow():
                # Extend from current end date
                user.subscription_end_date += timedelta(days=additional_days)
            else:
                # Start fresh from now
                user.subscription_end_date = datetime.utcnow() + timedelta(days=additional_days)

            user.is_active = True
            session.commit()
            logger.info(
                f"User {user_id} status renewed by {additional_days} days, "
                f"new expiry: {user.subscription_end_date}"
            )
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Error renewing status for user {user_id}: {e}")
            return False
        finally:
            session.close()


# Singleton instance
subscription_manager = SubscriptionManager()
