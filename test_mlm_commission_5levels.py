"""
Расширенный тест MLM комиссий для NANOREM.
Проверяет ВСЕ 5 УРОВНЕЙ маркетинг-плана:
- 1 уровень: 20%
- 2 уровень: 10%
- 3 уровень: 5%
- 4 уровень: 5%
- 5 уровень: 5%
"""

from database.db import SessionLocal
from database.models import Partner, Purchase, Commission, OrderStatus
from core.commission import CommissionCalculator
import uuid


def clean_test_data(session):
    """Очистка тестовых партнеров (telegram_id test_5level_*)"""
    session.query(Commission).delete()
    session.query(Purchase).delete()
    session.query(Partner).filter(
        Partner.telegram_id.like("test_5level_%")
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
    
    print(f"  ✅ Создан: ID={partner.id}, telegram={telegram_id}, upline={upline_id}, lineage={lineage}")
    return partner


async def run_5level_test():
    session = SessionLocal()

    try:
        # 1. Очистка старых тестовых данных
        clean_test_data(session)

        # 2. Получаем root'а (левый)
        root = session.query(Partner).filter(
            Partner.upline_id.is_(None)
        ).order_by(Partner.id).first()

        if not root:
            print("❌ Ошибка: нужен хотя бы один root-партнер в БД")
            return

        print(f"\n🌳 Root: ID={root.id}, telegram={root.telegram_id}")

        # 3. Создаем цепочку из 6 партнеров (root уже есть, создаем 5 новых)
        print("\n--- Создание цепочки из 6 партнеров (покупатель + 5 предков) ---")
        
        partners = [root]
        
        for i in range(1, 6):
            p = create_test_partner_direct(
                session,
                telegram_id=f"test_5level_{i}",
                upline_id=partners[-1].id
            )
            partners.append(p)
        
        # partners: [root, P1, P2, P3, P4, P5]
        # P5 - покупатель (последний в цепочке)
        
        buyer = partners[-1]  # P5
        
        print(f"\n📋 Цепочка создана:")
        for idx, p in enumerate(partners):
            role = "Root" if idx == 0 else f"Уровень {6-idx} от покупателя" if idx < 5 else "ПОКУПАТЕЛЬ"
            print(f"  [{idx}] ID={p.id} - {role}")

        # 4. Создаем покупку для P5
        print(f"\n--- Покупка для {buyer.telegram_id} (ID={buyer.id}) на 1000 руб ---")
        
        purchase = Purchase(
            purchase_number="TEST-5LEVEL-001",
            partner_id=buyer.id,
            amount=1000.0,
            status=OrderStatus.PAID,
        )
        session.add(purchase)
        session.commit()
        session.refresh(purchase)

        # 5. Запускаем расчет комиссий
        calculator = CommissionCalculator(session, bot=None)
        await calculator.process_purchase(purchase)

        # 6. Проверяем комиссии
        print("\n" + "=" * 60)
        print("📊 РЕЗУЛЬТАТЫ КОМИССИЙ ПО УРОВНЯМ")
        print("=" * 60)

        commissions = session.query(Commission).filter(
            Commission.purchase_id == purchase.id
        ).order_by(Commission.level).all()

        expected_levels = {
            1: {"partner_idx": 4, "rate": 20, "amount": 200},  # P4
            2: {"partner_idx": 3, "rate": 10, "amount": 100},  # P3
            3: {"partner_idx": 2, "rate": 5, "amount": 50},    # P2
            4: {"partner_idx": 1, "rate": 5, "amount": 50},    # P1
            5: {"partner_idx": 0, "rate": 5, "amount": 50},    # root
        }

        received_by_partner = {}
        for c in commissions:
            received_by_partner[c.partner_id] = c
            partner_idx = next((i for i, p in enumerate(partners) if p.id == c.partner_id), None)
            print(f"\n✅ Уровень {c.level}: ID={c.partner_id}, сумма={c.amount} руб, ставка={c.rate*100:.0f}%")
            if partner_idx is not None:
                role = "Root" if partner_idx == 0 else f"P{partner_idx}"
                print(f"   → Это {role} (индекс {partner_idx} в цепочке)")

        print("\n" + "=" * 60)
        print("✅ ПРОВЕРКИ")
        print("=" * 60)

        # Проверка 1: Покупатель (P5) не получил комиссию
        assert buyer.id not in received_by_partner, "❌ Покупатель получил комиссию!"
        print(f"✅ Покупатель (ID={buyer.id}) не получил комиссию")

        # Проверка 2-6: Каждый уровень получил правильную сумму
        for level, expected in expected_levels.items():
            expected_partner = partners[expected["partner_idx"]]
            expected_amount = expected["amount"]
            expected_rate = expected["rate"]
            
            comm = received_by_partner.get(expected_partner.id)
            assert comm is not None, f"❌ Уровень {level}: партнер ID={expected_partner.id} не получил комиссию"
            assert comm.amount == expected_amount, f"❌ Уровень {level}: ожидалось {expected_amount} руб, получено {comm.amount} руб"
            assert comm.rate * 100 == expected_rate, f"❌ Уровень {level}: ожидалась ставка {expected_rate}%, получено {comm.rate*100}%"
            assert comm.level == level, f"❌ Уровень {level}: записан как уровень {comm.level}"
            
            partner_name = "Root" if expected["partner_idx"] == 0 else f"P{expected['partner_idx']}"
            print(f"✅ {partner_name}: уровень {level}, ставка {expected_rate}%, сумма {expected_amount} руб")

        # Проверка 7: Всего создано 5 комиссий
        assert len(commissions) == 5, f"❌ Ожидалось 5 комиссий, получено {len(commissions)}"
        print(f"✅ Всего создано 5 комиссий (по одной на каждый уровень)")

        # Проверка 8: Общая сумма комиссий = 450 руб (200+100+50+50+50)
        total_commission = sum(c.amount for c in commissions)
        assert total_commission == 450.0, f"❌ Общая сумма комиссий должна быть 450 руб, получено {total_commission}"
        print(f"✅ Общая сумма комиссий: {total_commission} руб (45% от 1000 руб)")

        print("\n" + "=" * 60)
        print("🎉 ВСЕ ПРОВЕРКИ (5 УРОВНЕЙ) ПРОЙДЕНЫ УСПЕШНО!")
        print("=" * 60)

        # 9. Дополнительно: показываем lineage покупателя для информации
        print(f"\n📌 Lineage покупателя (ID={buyer.id}): {buyer.lineage}")
        print("   Это означает цепочку предков: P4 → P3 → P2 → P1 → Root")

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
    asyncio.run(run_5level_test())