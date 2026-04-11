from services.partner_service import PartnerService
from database.db import SessionLocal
from database.models import Partner


def run_test():
    session = SessionLocal()
    service = PartnerService()

    try:
        # 👉 создаём 6 пользователей БЕЗ реферала
        for i in range(1001, 1007):
            p = service.create_partner(telegram_id=i)
            print(f"created: {p.id} -> upline {p.upline_id}")

        print("\n--- STRUCTURE ---")

        partners = session.query(Partner).all()

        for p in partners:
            print(f"id={p.id}, upline={p.upline_id}")

    finally:
        session.close()


if __name__ == "__main__":
    run_test()