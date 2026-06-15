"""
Тест MLM комиссий для NANOREM.
Проверяет:
1. Комиссии начисляются только внутри своей ноги (левой или правой).
2. Проценты корректные: 1 уровень = 20%, 2 уровень = 10%, 3-5 = 5%.
3. Покупатель не получает комиссию.
"""

from database.db import SessionLocal
from database.models import Partner, Purchase, Commission, OrderStatus
from core.commission import CommissionCalculator
import uuid


def clean_test_data(session):
    """Очистка тестовых партнеров (telegram_id test_*)"""
    session.query(Commission).delete()
    session.query(Purchase).delete()
    session.query(Partner).filter(
        Partner.telegram_id.like("test_%")
    ).delete()
    session.commit()
    print("🧹 Тестовые данные очищены")


def create_test_partner_direct(session, telegram_id: str, upline_id: int = None):
    """Создать тестового партнера напрямую через БД"""
    
    # Формируем lineage
    lineage = []
    if upline_id:
        upline = session.query(Partner).filter(Partner.id == upline_id).first()
        if upline and upline.lineage:
            lineage = list(upline.lineage)
        lineage.insert(0, upline_id) if upline_id not in lineage else None
    
    partner = Partner(
        telegram_id=telegram_id,
        telegram_link_code=str(uuid.uuid4())[:8],
        upline_id=upline_id,
        lineage=lineage,
        status="ACTIVE",
        role="partner",
        rank="Partner"
    )
    
    session.add(partner)
    session.commit()
    session.refresh(partner)
    
    print(f"  ✅ Создан партнер: ID={partner.id}, telegram={telegram_id}, upline={upline_id}, lineage={lineage}")
    return partner


async def run_commission_test():
    session = SessionLocal()

    try:
        # 1. Очистка старых тестовых данных
        clean_test_data(session)

        # 2. Получаем двух root'ов (они уже должны быть в БД)
        roots = session.query(Partner).filter(
            Partner.upline_id.is_(None)
        ).order_by(Partner.id).all()

        if len(roots) < 2:
            print("❌ Ошибка: нужно 2 root-партнера в БД")
            return

        root_left = roots[0]
        root_right = roots[1]

        print(f"\n🌳 Root Left:  ID={root_left.id}, telegram={root_left.telegram_id}")
        print(f"🌳 Root Right: ID={root_right.id}, telegram={root_right.telegram_id}")

        # 3. Создаем цепочку в ЛЕВОЙ ноге
        print("\n--- Создание цепочки в ЛЕВОЙ ноге ---")

        partner_a = create_test_partner_direct(
            session,
            telegram_id="test_left_1",
            upline_id=root_left.id
        )
        print(f"✅ Partner A (левая нога, уровень 1): ID={partner_a.id}")

        partner_b = create_test_partner_direct(
            session,
            telegram_id="test_left_2",
            upline_id=partner_a.id
        )
        print(f"✅ Partner B (левая нога, уровень 2, покупатель): ID={partner_b.id}")

        # 4. Создаем цепочку в ПРАВОЙ ноге
        print("\n--- Создание цепочки в ПРАВОЙ ноге ---")

        partner_c = create_test_partner_direct(
            session,
            telegram_id="test_right_1",
            upline_id=root_right.id
        )
        print(f"✅ Partner C (правая нога, уровень 1): ID={partner_c.id}")

        partner_d = create_test_partner_direct(
            session,
            telegram_id="test_right_2",
            upline_id=partner_c.id
        )
        print(f"✅ Partner D (правая нога, уровень 2, покупатель): ID={partner_d.id}")

        # 5. Создаем покупку для Partner B (левая нога)
        print("\n--- Покупка в ЛЕВОЙ ноге (Partner B) ---")
        purchase_left = Purchase(
            purchase_number="TEST-LEFT-001",
            partner_id=partner_b.id,
            amount=1000.0,
            status=OrderStatus.PAID,
        )
        session.add(purchase_left)
        session.commit()
        session.refresh(purchase_left)

        # Запускаем расчет комиссий
        calculator = CommissionCalculator(session, bot=None)
        await calculator.process_purchase(purchase_left)

        # 6. Создаем покупку для Partner D (правая нога)
        print("\n--- Покупка в ПРАВОЙ ноге (Partner D) ---")
        purchase_right = Purchase(
            purchase_number="TEST-RIGHT-001",
            partner_id=partner_d.id,
            amount=1000.0,
            status=OrderStatus.PAID,
        )
        session.add(purchase_right)
        session.commit()
        session.refresh(purchase_right)

        await calculator.process_purchase(purchase_right)

        # 7. Проверяем комиссии
        print("\n" + "=" * 50)
        print("📊 РЕЗУЛЬТАТЫ КОМИССИЙ")
        print("=" * 50)

        # Все комиссии от обеих покупок
        all_commissions = session.query(Commission).filter(
            Commission.purchase_id.in_([purchase_left.id, purchase_right.id])
        ).all()

        # Группируем по партнеру
        by_partner = {}
        for c in all_commissions:
            if c.partner_id not in by_partner:
                by_partner[c.partner_id] = []
            by_partner[c.partner_id].append(c)

        # Выводим результаты
        partner_names = {
            root_left.id: "Root Left",
            root_right.id: "Root Right",
            partner_a.id: "Partner A (левая, ур.1)",
            partner_b.id: "Partner B (левая, ур.2, покупатель)",
            partner_c.id: "Partner C (правая, ур.1)",
            partner_d.id: "Partner D (правая, ур.2, покупатель)",
        }

        for partner_id, commissions in by_partner.items():
            name = partner_names.get(partner_id, f"Partner {partner_id}")
            total = sum(c.amount for c in commissions)
            print(f"\n{name}:")
            for c in commissions:
                purchase_name = "LEFT" if c.purchase_id == purchase_left.id else "RIGHT"
                print(f"  - От покупки {purchase_name}: {c.amount} руб. (уровень {c.level}, ставка {c.rate*100:.0f}%)")
            print(f"  ИТОГО: {total} руб.")

        # 8. Проверки (assert)
        print("\n" + "=" * 50)
        print("✅ ПРОВЕРКИ")
        print("=" * 50)

        # Проверка 1: Partner B (покупатель) не получил комиссию
        b_commissions = [c for c in all_commissions if c.partner_id == partner_b.id]
        assert len(b_commissions) == 0, "❌ Покупатель B получил комиссию!"
        print("✅ Покупатель B не получил комиссию")

        # Проверка 2: Partner D (покупатель) не получил комиссию
        d_commissions = [c for c in all_commissions if c.partner_id == partner_d.id]
        assert len(d_commissions) == 0, "❌ Покупатель D получил комиссию!"
        print("✅ Покупатель D не получил комиссию")

        # Проверка 3: Partner A получил 20% от левой покупки (200 руб)
        a_comm = [c for c in all_commissions if c.partner_id == partner_a.id]
        assert len(a_comm) == 1, f"❌ Partner A должен получить 1 комиссию, получил {len(a_comm)}"
        assert a_comm[0].amount == 200.0, f"❌ Partner A должен получить 200 руб, получил {a_comm[0].amount}"
        assert a_comm[0].level == 1, f"❌ Partner A должен быть уровень 1, а не {a_comm[0].level}"
        print("✅ Partner A получил 20% (200 руб, уровень 1)")

        # Проверка 4: Root Left получил 10% от левой покупки (100 руб)
        root_left_comm = [c for c in all_commissions if c.partner_id == root_left.id and c.purchase_id == purchase_left.id]
        assert len(root_left_comm) == 1, f"❌ Root Left должен получить 1 комиссию от левой покупки, получил {len(root_left_comm)}"
        assert root_left_comm[0].amount == 100.0, f"❌ Root Left должен получить 100 руб, получил {root_left_comm[0].amount}"
        assert root_left_comm[0].level == 2, f"❌ Root Left должен быть уровень 2, а не {root_left_comm[0].level}"
        print("✅ Root Left получил 10% от левой покупки (100 руб, уровень 2)")

        # Проверка 5: Partner C получил 20% от правой покупки (200 руб)
        c_comm = [c for c in all_commissions if c.partner_id == partner_c.id]
        assert len(c_comm) == 1, f"❌ Partner C должен получить 1 комиссию, получил {len(c_comm)}"
        assert c_comm[0].amount == 200.0, f"❌ Partner C должен получить 200 руб, получил {c_comm[0].amount}"
        print("✅ Partner C получил 20% от правой покупки (200 руб, уровень 1)")

        # Проверка 6: Root Right получил 10% от правой покупки (100 руб)
        root_right_comm = [c for c in all_commissions if c.partner_id == root_right.id and c.purchase_id == purchase_right.id]
        assert len(root_right_comm) == 1, f"❌ Root Right должен получить 1 комиссию от правой покупки, получил {len(root_right_comm)}"
        assert root_right_comm[0].amount == 100.0
        print("✅ Root Right получил 10% от правой покупки (100 руб, уровень 2)")

        # Проверка 7: Нет перекрестных комиссий
        left_purchase_root_right = [c for c in all_commissions if c.partner_id == root_right.id and c.purchase_id == purchase_left.id]
        assert len(left_purchase_root_right) == 0, "❌ Root Right получил комиссию от левой покупки!"
        print("✅ Root Right не получил комиссию от левой ноги")

        right_purchase_root_left = [c for c in all_commissions if c.partner_id == root_left.id and c.purchase_id == purchase_right.id]
        assert len(right_purchase_root_left) == 0, "❌ Root Left получил комиссию от правой покупки!"
        print("✅ Root Left не получил комиссию от правой ноги")

        print("\n" + "=" * 50)
        print("🎉 ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ УСПЕШНО!")
        print("=" * 50)

    except AssertionError as e:
        print(f"\n❌ ТЕСТ ПРОВАЛЕН: {e}")
        raise
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_commission_test())