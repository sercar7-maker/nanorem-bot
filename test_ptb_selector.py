import asyncio
import logging

if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from telegram import Bot
from config import BOT_TOKEN

logging.basicConfig(level=logging.DEBUG)


async def main():
    bot = Bot(token=BOT_TOKEN)
    me = await bot.get_me()
    print(me)


if __name__ == "__main__":
    asyncio.run(main())