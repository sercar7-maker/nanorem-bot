from database.models import Partner
from services.stats_service import StatsService
from telegram import Bot
from config import BOT_TOKEN


class RankService:

    RANKS = [
        ("Partner", 0),
        ("Silver", 10000),
        ("Gold", 50000),
        ("Platinum", 100000),
    ]

    def __init__(self, session):
        self.session = session
        self.bot = Bot(token=BOT_TOKEN)

    def calculate_rank(self, personal_turnover: float) -> str:

        current_rank = "Partner"

        for rank, threshold in self.RANKS:
            if personal_turnover >= threshold:
                current_rank = rank

        return current_rank

    def update_partner_rank(self, partner, new_rank: str):

        if partner.rank != new_rank:
            old_rank = partner.rank
            partner.rank = new_rank
            self.session.commit()
            return old_rank, new_rank

        return None, None

    async def process_rank(self, partner):

        stats_service = StatsService(self.session)

        # ✅ исправили метод
        stats = stats_service._get_or_create_stats(partner.id)

        new_rank = self.calculate_rank(stats.personal_turnover)

        old_rank, updated_rank = self.update_partner_rank(
            partner, new_rank
        )

        # -------------------------------------------------
        # 🔔 УВЕДОМЛЕНИЕ
        # -------------------------------------------------

        if updated_rank and partner.telegram_id:
            try:
                await self.bot.send_message(
                    chat_id=partner.telegram_id,
                    text=(
                        "🎉 Поздравляем!\n\n"
                        f"Ваш новый ранг: {updated_rank}\n\n"
                        "Продолжайте развитие 🚀"
                    )
                )
            except Exception as e:
                print(f"Telegram error: {e}")

        return old_rank, updated_rank