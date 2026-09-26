import logging
import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

def format_listing_message(listing: dict, event_type: str = "new") -> str:
    """Formatting ad data to a Telegram message."""
    emoji_header = "\U0001F195**Novi oglas u Osijeku**\U0001F195" if event_type == "new" else "\U0001F4C9**Sniženje cijene!**\U0001F4C9"

    area_info = f"{listing['area_sqm']} m2" if listing.get("area_sqm") else "Nije navedeno"

    message = (
        f"{emoji_header}\n\n"
        f"\U0001F3E2 **{listing['title']}**"
        f"\U0001F4B0 **{listing['price']:.2f}**"
        f"\U0001F4D0 **{area_info}**"
        f"\U0001F517 \U000027A1 [Pogledaj oglas na index.hr]({listing['url']})"
    )
    return message

def send_telegram_notification(listing: dict, event_type: str = "new") -> bool:
    """Sending message to Telegram chat."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("\u274C Telegram bot token or chat id not defined in .env file")

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    text = format_listing_message(listing, event_type)

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        logging.error(f"\u274C Notification sent unsuccessfully to Telegram: {e}")
        return False