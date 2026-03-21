import os
import requests
import telebot
import logging

for key in [
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "all_proxy",
    "NO_PROXY", "no_proxy"
]:
    os.environ.pop(key, None)

os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

from config import BOT_TOKEN

logging.basicConfig(level=logging.DEBUG)

session = requests.Session()
session.trust_env = False
session.proxies = {}

bot = telebot.TeleBot(BOT_TOKEN)
telebot.apihelper.SESSION = session

print("SESSION TRUST_ENV:", session.trust_env)
print("SESSION PROXIES:", session.proxies)
print("START get_me()")

try:
    result = bot.get_me()
    print("SUCCESS:")
    print(result)
except Exception as e:
    print("ERROR TYPE:", type(e).__name__)
    print("ERROR TEXT:", e)