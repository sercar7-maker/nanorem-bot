"""Scheduler for automatic background tasks in NANOREM MLM bot.

This module implements periodic tasks such as:
- Automatic status expiration (Сгорание статуса / Активация)
- Daily commission summary notifications
- Database cleanup

Uses APScheduler for async task scheduling.
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from core.subscription_manager import subscription_manager

logger = logging.getLogger(__name__)

# Scheduler instance (singleton)
_scheduler: AsyncIOScheduler = None


async def expire_statuses_job() -> None:
    """
    Periodic job: check and expire partner statuses.
    Runs every hour to catch any partners whose subscription_end_date has passed.
    """
    try:
        expired_count = subscription_manager.check_and_expire_statuses()
        if expired_count > 0:
            logger.info(
                f"[Scheduler] Expired {expired_count} partner status(es) "
                f"(Сгорание статуса)"
            )
        else:
            logger.debug("[Scheduler] Status expiration check: no expired partners")
    except Exception as e:
        logger.error(f"[Scheduler] Error in expire_statuses_job: {e}")


async def daily_summary_job() -> None:
    """
    Periodic job: log daily summary of active vs inactive partners.
    Runs every day at 00:05 UTC.
    """
    try:
        from database.db import get_session
        from database.models import Partner, PartnerStatus

        session = get_session()
        try:
            active_count = (
                session.query(Partner)
                .filter(Partner.status == PartnerStatus.ACTIVE)
                .count()
            )
            inactive_count = (
                session.query(Partner)
                .filter(Partner.status == PartnerStatus.INACTIVE)
                .count()
            )
            total = active_count + inactive_count
            logger.info(
                f"[Scheduler] Daily summary: "
                f"Total={total}, Active={active_count}, Inactive={inactive_count}"
            )
        finally:
            session.close()
    except Exception as e:
        logger.error(f"[Scheduler] Error in daily_summary_job: {e}")


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


def setup_scheduler() -> AsyncIOScheduler:
    """
    Configure and return the scheduler with all periodic jobs.
    Call this once at startup before starting the scheduler.
    """
    scheduler = get_scheduler()

    # Job 1: Check and expire statuses every hour
    scheduler.add_job(
        expire_statuses_job,
        trigger=IntervalTrigger(hours=1),
        id="expire_statuses",
        name="Expire partner statuses (Сгорание статуса)",
        replace_existing=True,
        max_instances=1,
    )

    # Job 2: Daily summary at 00:05 UTC
    scheduler.add_job(
        daily_summary_job,
        trigger=CronTrigger(hour=0, minute=5, timezone="UTC"),
        id="daily_summary",
        name="Daily partner summary",
        replace_existing=True,
        max_instances=1,
    )

    logger.info(
        "[Scheduler] Configured jobs: expire_statuses (every 1h), "
        "daily_summary (daily at 00:05 UTC)"
    )
    return scheduler


def start_scheduler() -> AsyncIOScheduler:
    """
    Setup and start the scheduler.
    Returns the running scheduler instance.
    """
    scheduler = setup_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("[Scheduler] Started successfully")
    return scheduler


def stop_scheduler() -> None:
    """Gracefully stop the scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Stopped")
