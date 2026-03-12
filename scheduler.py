import logging
from apscheduler.schedulers.background import BackgroundScheduler

from services.monthly_reset_service import MonthlyResetService

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="UTC")


# -------------------------------------------------
# Existing jobs
# -------------------------------------------------

def expire_statuses():
    """
    Example placeholder for status expiration logic.
    Replace with real implementation if needed.
    """
    logger.info("[Scheduler] Running expire_statuses job")


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

    # Every hour
    scheduler.add_job(
        expire_statuses,
        "interval",
        hours=1,
        id="expire_statuses"
    )

    # Daily summary
    scheduler.add_job(
        daily_summary,
        "cron",
        hour=0,
        minute=5,
        id="daily_summary"
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
        id="monthly_reset_turnover"
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

    setup_scheduler()

    scheduler.start()

    logger.info("[Scheduler] Scheduler started")