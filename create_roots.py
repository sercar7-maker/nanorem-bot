from database.db import get_session
from database.models import Partner


def create_partner(session, telegram_id, first_name):
    partner = session.query(Partner).filter(
        Partner.telegram_id == telegram_id
    ).first()

    if partner:
        print(f"{first_name} уже существует")
        return partner

    partner = Partner(
        telegram_id=telegram_id,
        first_name=first_name,
        last_name="Root",
        upline_id=None  # корень
    )

    session.add(partner)
    session.commit()

    print(f"{first_name} создан")
    return partner


def main():
    with get_session() as session:

        # 👤 Ты
        create_partner(session, "899738024", "Sergey")

        # 🏭 Производитель
        create_partner(session, "111111111", "Factory")


if __name__ == "__main__":
    main()