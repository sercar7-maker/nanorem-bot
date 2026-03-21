import os
import asyncio
import httpx

for key in [
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "all_proxy",
    "NO_PROXY", "no_proxy"
]:
    os.environ.pop(key, None)

os.environ["NO_PROXY"] = "*"


async def main():
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        response = await client.get("https://api.telegram.org")
        print("STATUS:", response.status_code)
        print("TEXT:", response.text[:200])


asyncio.run(main())