import os
import requests
import logging
from config import BOT_TOKEN

for key in [
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "all_proxy",
    "NO_PROXY", "no_proxy"
]:
    os.environ.pop(key, None)

os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

logging.basicConfig(level=logging.DEBUG)

url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"

try:
    response = requests.get(
        url,
        timeout=30,
        proxies={"http": None, "https": None},
        verify=False
    )
    print("STATUS:", response.status_code)
    print("TEXT:", response.text)
except Exception as e:
    print("ERROR TYPE:", type(e).__name__)
    print("ERROR TEXT:", e)