from sqlalchemy.orm import Session
from database.models import Partner


def get_active_uplines(
    session: Session,
    buyer: Partner,
    max_levels: int = 5
):
    """
    Возвращает список активных аплайнов для MLM-комиссий.
    Пропускает неактивных партнёров (компрессия).
    """

    uplines = []
    current = buyer.upline

    while current and len(uplines) < max_levels:

        if current.status == "active":
            uplines.append(current)

        current = current.upline

    return uplines