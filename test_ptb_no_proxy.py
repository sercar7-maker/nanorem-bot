import os
import asyncio
import logging

if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

for key in [
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "all_proxy",
    "NO_PROXY", "no_proxy",
]:
    os.environ.pop(key, None)

os.environ["NO_PROXY"] = "*"

from config import BOT_TOKEN
from telegram import Bot
from telegram.request import HTTPXRequest

logging.basicConfig(level=logging.DEBUG)


async def main():
    request = HTTPXRequest(
        connection_pool_size=1,
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0,
        http_version="1.1",
        proxy=None,
    )

    bot = Bot(token=BOT_TOKEN, request=request)
    me = await bot.get_me()
    print(me)


if __name__ == "__main__":
    asyncio.run(main())