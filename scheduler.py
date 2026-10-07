import logging
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from database.db import SessionLocal
from services.monthly_reset_service import MonthlyResetService
from services.structural_compression_service import (
    StructuralCompressionService,
)

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="UTC")


# -------------------------------------------------
# Existing jobs
# -------------------------------------------------

def expire_statuses():
    session = SessionLocal()
    try:
        expired_count = StructuralCompressionService(
            session
        ).expire_due_partners(datetime.now(timezone.utc))
        session.commit()
        logger.info(
            "[Scheduler] Expired and compressed %s partner subscriptions",
            expired_count,
        )
    except Exception:
        session.rollback()
        logger.exception("[Scheduler] Failed to expire partner statuses")
        raise
    finally:
        session.close()


def daily_summary():
    """
    Example placeholder for daily summary logic.
    Replace with real implementation if needed.
    """
    logger.info("[Scheduler] Running daily_summary job")


# -------------------------------------------------
# Configure jobs
# -------------------------------------------------

def setup_scheduler():

    # Process expirations frequently so structural compression follows expiry.
    scheduler.add_job(
        expire_statuses,
        "interval",
        minutes=1,
        id="expire_statuses",
        replace_existing=True,
    )

    # Daily summary
    scheduler.add_job(
        daily_summary,
        "cron",
        hour=0,
        minute=5,
        id="daily_summary",
        replace_existing=True,
    )

    # -------------------------------------------------
    # Monthly turnover reset
    # -------------------------------------------------

    scheduler.add_job(
        MonthlyResetService.reset_monthly_turnover,
        "cron",
        day=1,
        hour=0,
        minute=5,
        id="monthly_reset_turnover",
        replace_existing=True,
    )

    logger.info(
        "[Scheduler] Configured jobs: expire_statuses (every 1h), "
        "daily_summary (daily at 00:05 UTC), "
        "monthly_reset_turnover (1st day of month at 00:05 UTC)"
    )


# -------------------------------------------------
# Start scheduler
# -------------------------------------------------

def start_scheduler():
    if scheduler.running:
        return

    setup_scheduler()

    scheduler.start()

    logger.info("[Scheduler] Scheduler started")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)