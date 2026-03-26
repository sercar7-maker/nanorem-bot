import httpx
import os
from dotenv import load_dotenv

# загружаем .env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

print("TOKEN:", BOT_TOKEN)

url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"

print("START TELEGRAM TEST")

try:
    response = httpx.get(url, timeout=10)
    print("STATUS:", response.status_code)
    print("RESPONSE:", response.text)
except Exception as e:
    print("ERROR:", repr(e))

print("END TEST")