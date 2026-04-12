from services.partner_service import PartnerService
from database.db import SessionLocal
from database.models import Partner


def run_test():
    session = SessionLocal()
    service = PartnerService()

    try:
        # 👉 создаём 6 пользователей БЕЗ реферала
        for i in range(2001, 2007):  # ← ИЗМЕНИЛИ НА 2001-2006
            p = service.create_partner(telegram_id=str(i))  # ← ПРИВЕЛИ К СТРОКЕ
            print(f"created: {p.id} -> upline {p.upline_id}")

        print("\n--- STRUCTURE ---")

        partners = session.query(Partner).filter(
            Partner.telegram_id.in_([str(i) for i in range(2001, 2007)])
        ).all()

        for p in partners:
            print(f"id={p.id}, telegram_id={p.telegram_id}, upline={p.upline_id}")

    finally:
        session.close()


if __name__ == "__main__":
    run_test()