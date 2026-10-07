from calendar import monthrange
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models import (
    OrderStatus,
    Partner,
    PartnerStatus,
    Purchase,
)
from services.root_allocation_lock import acquire_root_allocation_lock

MONTHLY_PURCHASE_AMOUNT = Decimal("3000.00")
ANNUAL_PURCHASE_AMOUNT = Decimal("10000.00")


def _as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).replace(tzinfo=None)
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _add_calendar_months(value: datetime, months: int) -> datetime:
    month_index = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(month_index, 12)
    month = month_index + 1
    last_day = monthrange(year, month)[1]
    source_is_month_end = value.day == monthrange(value.year, value.month)[1]
    day = last_day if source_is_month_end else min(value.day, last_day)
    return value.replace(year=year, month=month, day=day)


class SubscriptionService:
    """Applies activity periods to the existing partner expiry field."""

    def __init__(self, session: Session):
        self.session = session

    def apply_purchase(self, purchase: Purchase) -> datetime | None:
        acquire_root_allocation_lock(self.session)

        partner = self.session.get(Partner, purchase.partner_id)
        if partner is None:
            raise ValueError(f"Partner {purchase.partner_id} was not found")
        self.session.refresh(
            partner,
            attribute_names=[
                "subscription_end_date",
                "annual_activity_until",
            ],
        )
        if purchase.status != OrderStatus.PAID:
            raise ValueError("Only paid purchases can renew partner activity")

        purchased_at = _as_utc_naive(
            purchase.paid_at
            or purchase.created_at
            or datetime.now(timezone.utc)
        )

        if partner.root_id == partner.id:
            return partner.subscription_end_date

        annual_until = (
            _as_utc_naive(partner.annual_activity_until)
            if partner.annual_activity_until is not None
            else None
        )
        if annual_until is not None and annual_until > purchased_at:
            return partner.subscription_end_date
        if annual_until is not None:
            partner.annual_activity_until = None

        month_start = purchased_at.replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        next_month_start = _add_calendar_months(month_start, 1)

        month_purchases = (
            self.session.query(Purchase)
            .filter(
                Purchase.partner_id == purchase.partner_id,
                Purchase.status == OrderStatus.PAID,
                func.coalesce(
                    Purchase.paid_at,
                    Purchase.created_at,
                ) >= month_start,
                func.coalesce(
                    Purchase.paid_at,
                    Purchase.created_at,
                ) < next_month_start,
            )
            .all()
        )
        month_purchases.sort(
            key=lambda item: (
                _as_utc_naive(
                    item.paid_at
                    or item.created_at
                    or datetime.now(timezone.utc)
                ),
                item.id,
            )
        )
        month_total = sum(
            (Decimal(str(item.amount)) for item in month_purchases),
            start=Decimal("0.00"),
        )

        existing_end = (
            _as_utc_naive(partner.subscription_end_date)
            if partner.subscription_end_date is not None
            else None
        )

        if Decimal(str(purchase.amount)) >= ANNUAL_PURCHASE_AMOUNT:
            new_end = _add_calendar_months(purchased_at, 12)
        elif month_total >= ANNUAL_PURCHASE_AMOUNT:
            accumulated = Decimal("0.00")
            threshold_date = month_purchases[-1].paid_at or month_purchases[-1].created_at
            for month_purchase in month_purchases:
                accumulated += Decimal(str(month_purchase.amount))
                if accumulated >= ANNUAL_PURCHASE_AMOUNT:
                    threshold_date = (
                        month_purchase.paid_at
                        or month_purchase.created_at
                    )
                    break
            new_end = _add_calendar_months(
                _as_utc_naive(threshold_date),
                12,
            )
        elif Decimal(str(purchase.amount)) == MONTHLY_PURCHASE_AMOUNT:
            extension_from = max(
                value
                for value in (existing_end, purchased_at)
                if value is not None
            )
            new_end = _add_calendar_months(extension_from, 1)
        else:
            new_end = existing_end

        if existing_end is not None and (
            new_end is None or existing_end > new_end
        ):
            new_end = existing_end

        partner.subscription_end_date = new_end
        if (
            Decimal(str(purchase.amount)) >= ANNUAL_PURCHASE_AMOUNT
            or month_total >= ANNUAL_PURCHASE_AMOUNT
        ):
            partner.annual_activity_until = new_end

        if (
            new_end is not None
            and new_end > _as_utc_naive(datetime.now(timezone.utc))
            and partner.status in {
                PartnerStatus.INACTIVE,
                PartnerStatus.INACTIVE.name,
                PartnerStatus.INACTIVE.value,
            }
        ):
            partner.status = PartnerStatus.ACTIVE

        self.session.flush()
        return new_end
