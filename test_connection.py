def main():
    import os

    import httpx
    from dotenv import load_dotenv

    load_dotenv()
    bot_token = os.getenv("BOT_TOKEN")

    if not bot_token:
        raise RuntimeError("BOT_TOKEN is not configured")

    url = f"https://api.telegram.org/bot{bot_token}/getMe"

    print("START TELEGRAM TEST")

    try:
        response = httpx.get(url, timeout=10)
        print("STATUS:", response.status_code)
        print("RESPONSE:", response.text)
    except httpx.HTTPError as error:
        print("ERROR:", type(error).__name__)

    print("END TEST")


if __name__ == "__main__":
    main()