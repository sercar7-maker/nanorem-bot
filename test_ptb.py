import os
import asyncio

# Сносим все возможные proxy-переменные ДО импорта telegram
for key in [
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "all_proxy",
    "NO_PROXY", "no_proxy"
]:
    os.environ.pop(key, None)

os.environ["NO_PROXY"] = "*"

print("PROXY ENV CHECK:")
for key in [
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "all_proxy",
    "NO_PROXY", "no_proxy"
]:
    print(f"{key} =", os.environ.get(key))

from telegram import Bot
from config import BOT_TOKEN


async def main():
    bot = Bot(token=BOT_TOKEN)
    me = await bot.get_me()
    print(me)


asyncio.run(main())