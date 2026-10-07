from calendar import monthrange
from datetime import datetime, timezone
import logging

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from database.models import (
    OrderStatus,
    Partner,
    PartnerRecoveryChild,
    PartnerRecoveryEvent,
    PartnerStatus,
    Purchase,
)
from services.root_allocation_lock import acquire_root_allocation_lock

logger = logging.getLogger(__name__)


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).replace(tzinfo=None)
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _add_calendar_months(value: datetime, months: int) -> datetime:
    month_index = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(month_index, 12)
    month = month_index + 1
    last_day = monthrange(year, month)[1]
    day = (
        last_day
        if value.day == monthrange(value.year, value.month)[1]
        else min(value.day, last_day)
    )
    return value.replace(year=year, month=month, day=day)


def _is_active_status(status) -> bool:
    return status in {
        PartnerStatus.ACTIVE,
        PartnerStatus.ACTIVE.name,
        PartnerStatus.ACTIVE.value,
    }


def _is_root_partner(partner: Partner) -> bool:
    return partner.root_id == partner.id or (
        partner.root_id is None and partner.upline_id is None
    )


class RecoveryConflictError(RuntimeError):
    """Raised when restoring a placement would overwrite later tree changes."""


class StructuralCompressionService:
    """Mutates the current upline/lineage tree and records reversible snapshots."""

    def __init__(self, session: Session):
        self.session = session

    def ensure_root_affiliation(self, partner: Partner) -> int:
        if partner.root_id is not None:
            root = self.session.get(Partner, partner.root_id)
            if root is None:
                raise ValueError(
                    f"Partner {partner.id} references missing root "
                    f"{partner.root_id}"
                )
            return root.id

        path = []
        current = partner
        visited = set()
        while current.upline_id is not None:
            if current.id in visited:
                raise ValueError(
                    f"Cycle detected while resolving root for partner "
                    f"{partner.id}"
                )
            visited.add(current.id)
            path.append(current)
            parent = self.session.get(Partner, current.upline_id)
            if parent is None:
                raise ValueError(
                    f"Partner {current.id} references missing upline "
                    f"{current.upline_id}"
                )
            if parent.root_id is not None:
                root = self.session.get(Partner, parent.root_id)
                if root is None:
                    raise ValueError(
                        f"Partner {parent.id} references missing root "
                        f"{parent.root_id}"
                    )
                for descendant in path:
                    descendant.root_id = root.id
                partner.root_id = root.id
                return root.id
            current = parent

        root_id = current.id
        current.root_id = root_id
        for descendant in path:
            descendant.root_id = root_id
        partner.root_id = root_id
        return root_id

    def expire_due_partners(
        self,
        now: datetime | None = None,
    ) -> int:
        now_utc = _utc_naive(now or datetime.now(timezone.utc))
        acquire_root_allocation_lock(self.session)
        partners = (
            self.session.query(Partner)
            .filter(
                Partner.status == PartnerStatus.ACTIVE,
                or_(
                    and_(
                        Partner.root_id.is_(None),
                        Partner.upline_id.is_not(None),
                    ),
                    and_(
                        Partner.root_id.is_not(None),
                        Partner.root_id != Partner.id,
                    ),
                ),
                (
                    Partner.subscription_end_date.is_(None)
                    | (Partner.subscription_end_date <= now_utc)
                ),
            )
            .order_by(Partner.id)
            .all()
        )

        expired = 0
        for partner in partners:
            if self.compress_partner(
                partner,
                lost_activity_at=(
                    _utc_naive(partner.subscription_end_date)
                    if partner.subscription_end_date is not None
                    else now_utc
                ),
                lock_already_held=True,
            ):
                expired += 1
        return expired

    def compress_if_due_before_purchase(
        self,
        partner: Partner,
        purchase_at: datetime,
    ) -> bool:
        if (
            _is_root_partner(partner)
            or not _is_active_status(partner.status)
            or partner.subscription_end_date is None
            or _utc_naive(partner.subscription_end_date)
            > _utc_naive(purchase_at)
        ):
            return False

        return self.compress_partner(
            partner,
            lost_activity_at=_utc_naive(partner.subscription_end_date),
        )

    def compress_partner(
        self,
        partner: Partner,
        *,
        lost_activity_at: datetime,
        lock_already_held: bool = False,
    ) -> bool:
        if not lock_already_held:
            acquire_root_allocation_lock(self.session)

        self.session.refresh(partner)
        if _is_root_partner(partner):
            return False
        if not _is_active_status(partner.status):
            return False

        root_id = self.ensure_root_affiliation(partner)
        partner.status = PartnerStatus.INACTIVE

        if partner.id == root_id or partner.upline_id is None:
            self.session.flush()
            return True

        if (
            self.session.query(PartnerRecoveryEvent.id)
            .filter(
                PartnerRecoveryEvent.partner_id == partner.id,
                PartnerRecoveryEvent.status == "PENDING",
            )
            .first()
        ):
            self.session.flush()
            return True

        old_parent = self.session.get(Partner, partner.upline_id)
        if old_parent is None:
            raise ValueError(
                f"Partner {partner.id} has missing upline {partner.upline_id}"
            )
        if self.ensure_root_affiliation(old_parent) != root_id:
            raise ValueError(
                f"Partner {partner.id} and its upline belong to different roots"
            )

        children = (
            self.session.query(Partner)
            .filter(Partner.upline_id == partner.id)
            .order_by(Partner.id)
            .all()
        )
        lost_at = _utc_naive(lost_activity_at)
        event = PartnerRecoveryEvent(
            partner_id=partner.id,
            root_id=root_id,
            old_upline_id=old_parent.id,
            old_parent_lineage=list(old_parent.lineage or []),
            lost_activity_at=lost_at,
            recovery_until=_add_calendar_months(lost_at, 3),
            compressed_at=_utc_naive(datetime.now(timezone.utc)),
            compressed_partner_version=partner.placement_version + 1,
            old_parent_version=old_parent.placement_version,
            status="PENDING",
        )
        self.session.add(event)

        for child in children:
            child.upline_id = old_parent.id
            child.placement_version += 1

        partner.upline_id = None
        partner.lineage = []
        partner.placement_version += 1
        self.session.flush()

        for child in children:
            self.session.add(
                PartnerRecoveryChild(
                    recovery_event_id=event.id,
                    child_partner_id=child.id,
                    compressed_placement_version=child.placement_version,
                )
            )
            self._refresh_subtree_lineage(child)

        self.session.flush()
        logger.info(
            "Compressed inactive partner %s under original upline %s; "
            "recovery is available through %s",
            partner.id,
            old_parent.id,
            event.recovery_until.isoformat(),
        )
        return True

    def process_paid_purchase(self, partner: Partner, purchase: Purchase) -> bool:
        if purchase.status != OrderStatus.PAID:
            raise ValueError("Only paid purchases can recover placement")
        if not partner.is_active:
            return False

        acquire_root_allocation_lock(self.session)
        event = (
            self.session.query(PartnerRecoveryEvent)
            .filter(
                PartnerRecoveryEvent.partner_id == partner.id,
                PartnerRecoveryEvent.status == "PENDING",
            )
            .order_by(PartnerRecoveryEvent.id.desc())
            .first()
        )
        if event is None:
            return False

        purchase_at = _utc_naive(
            purchase.paid_at
            or purchase.created_at
            or datetime.now(timezone.utc)
        )
        if purchase_at <= _utc_naive(event.recovery_until):
            self._restore_snapshot(partner, event)
            event.status = "RESTORED"
            self.session.flush()
            logger.info(
                "Restored partner %s to previous placement from recovery "
                "event %s",
                partner.id,
                event.id,
            )
            return True

        root = self.session.get(Partner, event.root_id)
        if root is None or root.id != self.ensure_root_affiliation(root):
            raise ValueError(
                f"Recovery event {event.id} references invalid root "
                f"{event.root_id}"
            )
        if root.upline_id is not None:
            raise ValueError(
                f"Stored root {root.id} is no longer a root partner"
            )
        if partner.id == root.id:
            raise ValueError("A root partner cannot be placed under itself")

        partner.root_id = root.id
        partner.upline_id = root.id
        partner.placement_version += 1
        self._refresh_subtree_lineage(partner)
        event.status = "EXPIRED"
        self.session.flush()
        logger.info(
            "Placed late-reactivated partner %s directly under root %s",
            partner.id,
            root.id,
        )
        return True

    def _restore_snapshot(
        self,
        partner: Partner,
        event: PartnerRecoveryEvent,
    ) -> None:
        old_parent = self.session.get(Partner, event.old_upline_id)
        if old_parent is None:
            raise RecoveryConflictError(
                f"Recovery event {event.id}: previous upline no longer exists"
            )

        children = (
            self.session.query(PartnerRecoveryChild)
            .filter(
                PartnerRecoveryChild.recovery_event_id == event.id
            )
            .order_by(PartnerRecoveryChild.child_partner_id)
            .all()
        )
        child_partners = [
            self.session.get(Partner, child.child_partner_id)
            for child in children
        ]

        conflicts = []
        if (
            partner.root_id != event.root_id
            or partner.upline_id is not None
            or partner.placement_version
            != event.compressed_partner_version
        ):
            conflicts.append("partner placement changed")
        if (
            old_parent.root_id != event.root_id
            or old_parent.placement_version != event.old_parent_version
            or list(old_parent.lineage or [])
            != list(event.old_parent_lineage or [])
        ):
            conflicts.append("previous upline placement changed")

        for snapshot, child in zip(children, child_partners):
            if child is None:
                conflicts.append(
                    f"snapshot child {snapshot.child_partner_id} is missing"
                )
            elif (
                child.root_id != event.root_id
                or child.upline_id != old_parent.id
                or child.placement_version
                != snapshot.compressed_placement_version
            ):
                conflicts.append(
                    f"snapshot child {child.id} placement changed"
                )

        if conflicts:
            message = (
                f"Recovery event {event.id} for partner {partner.id} "
                f"cannot be safely restored: {'; '.join(conflicts)}"
            )
            logger.error(message)
            raise RecoveryConflictError(message)

        partner.upline_id = old_parent.id
        partner.placement_version += 1
        for child in child_partners:
            child.upline_id = partner.id
            child.placement_version += 1

        self._refresh_subtree_lineage(partner)

    def _refresh_subtree_lineage(self, root: Partner) -> None:
        if root.upline_id is None:
            root.lineage = []
        else:
            parent = self.session.get(Partner, root.upline_id)
            if parent is None:
                raise ValueError(
                    f"Partner {root.id} references missing upline "
                    f"{root.upline_id}"
                )
            root.lineage = [parent.id, *(parent.lineage or [])]
        root_id = self.ensure_root_affiliation(root)
        frontier = [root]
        visited = {root.id}

        while frontier:
            parent = frontier.pop(0)
            children = (
                self.session.query(Partner)
                .filter(Partner.upline_id == parent.id)
                .order_by(Partner.id)
                .all()
            )
            for child in children:
                if child.id in visited:
                    raise ValueError(
                        f"Cycle detected while refreshing lineage at "
                        f"partner {child.id}"
                    )
                visited.add(child.id)
                if (
                    child.root_id is not None
                    and child.root_id != root_id
                ):
                    raise ValueError(
                        f"Partner {child.id} cannot change root affiliation "
                        f"from {child.root_id} to {root_id}"
                    )
                child.root_id = root_id
                child.lineage = [parent.id, *(parent.lineage or [])]
                frontier.append(child)
