from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models import Partner, PartnerStatus
from web.auth_api import get_auth_db, require_admin_partner

router = APIRouter(prefix="/admin", tags=["admin"])

_PARTNER_FIELDS = (
    "id",
    "first_name",
    "last_name",
    "email",
    "phone",
    "role",
    "status",
    "root_id",
    "upline_id",
    "is_permanent_root",
    "is_active",
)


def serialize_partner_status(status) -> str:
    if isinstance(status, PartnerStatus):
        return status.value
    if isinstance(status, str):
        for item in PartnerStatus:
            if status == item.value or status == item.name:
                return item.value
    return str(status)


def serialize_partner(partner: Partner) -> dict:
    return {
        "id": partner.id,
        "first_name": partner.first_name,
        "last_name": partner.last_name,
        "email": partner.email,
        "phone": partner.phone,
        "role": partner.role,
        "status": serialize_partner_status(partner.status),
        "root_id": partner.root_id,
        "upline_id": partner.upline_id,
        "is_permanent_root": bool(partner.is_permanent_root),
        "is_active": bool(partner.is_active),
    }


@router.get("/partners")
def list_partners(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: Partner = Depends(require_admin_partner),
    session: Session = Depends(get_auth_db),
):
    total = session.query(func.count(Partner.id)).scalar() or 0
    partners = (
        session.query(Partner)
        .order_by(Partner.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    items = [serialize_partner(partner) for partner in partners]
    for item in items:
        if set(item) != set(_PARTNER_FIELDS):
            raise RuntimeError("Partner list fields drifted from the allowed set")
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
