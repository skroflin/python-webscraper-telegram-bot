import logging
import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from database.database import get_connectivity


def format_listing_message(listing: dict, event_type: str = "new") -> str:
    if event_type == "price_drop":
        old_price = listing.get("old_price", listing["price"])
        emoji_header = (
            "\U0001F4C9 **Sniženje cijene u Osijeku!** \U0001F4C9\n"
            f"Stara cijena: ~~{old_price:.2f} €~~ ➡️ Nova cijena: **{listing['price']:.2f} €**"
        )
    else:
        emoji_header = "\U0001F195 **Novi oglas u Osijeku** \U0001F195"

    area_info = f"{listing['area_sqm']} m²" if listing.get("area_sqm") else "Nije navedeno"
    platform_name = listing.get("source_platform", "oglasniku")

    message = (
        f"{emoji_header}\n\n"
        f"\U0001F3E2 **{listing['title']}**\n"
        f"\U0001F4B0 **Cijena: {listing['price']:.2f} €**\n"
        f"\U0001F4D0 **Površina/Kvadratura: {area_info}**\n"
        f"\U0001F517 [Pogledaj oglas na {platform_name}]({listing['url']})"
    )
    return message


def get_target_chat_ids(listing: dict) -> list:
    target_ids = set()

    try:
        with get_connectivity() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT telegram_id, max_price, min_area FROM users")
            users = cursor.fetchall()

        price = listing.get("price", 0)
        area = listing.get("area_sqm")

        for user in users:
            chat_id = user["telegram_id"]
            max_price = user["max_price"]
            min_area = user["min_area"]

            if max_price is not None and price > max_price:
                continue

            if min_area is not None and area is not None and area < min_area:
                continue

            target_ids.add(chat_id)

    except Exception as e:
        logging.error(f"\u274c Error fetching user filters: {e}")

    if not target_ids and TELEGRAM_CHAT_ID:
        try:
            target_ids.add(int(TELEGRAM_CHAT_ID))
        except ValueError:
            target_ids.add(TELEGRAM_CHAT_ID)

    return list(target_ids)


def send_telegram_notification(listing: dict, event_type: str = "new") -> bool:
    if not TELEGRAM_BOT_TOKEN:
        logging.error("\u274c TELEGRAM_BOT_TOKEN is not defined.")
        return False

    chat_ids = get_target_chat_ids(listing)
    if not chat_ids:
        logging.info(f"\u2139\ufe0f No users match criteria for listing: {listing['title']}")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    text = format_listing_message(listing, event_type)

    success_count = 0
    for chat_id in chat_ids:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            success_count += 1
        except Exception as e:
            logging.error(f"\u274c Failed to send notification to chat {chat_id}: {e}")

    return success_count > 0

def send_telegram_notification(listing: dict, event_type: str = "new") -> bool:
    if not TELEGRAM_BOT_TOKEN:
        logging.error("\u274c TELEGRAM_BOT_TOKEN is not defined.")
        return False

    chat_ids = get_target_chat_ids(listing)
    if not chat_ids:
        logging.info(f"\u2139\ufe0f No users match criteria for listing: {listing['title']}")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    text = format_listing_message(listing, event_type)

    inline_keyboard = [
        [{"text": "Pogledaj oglas \U0001F517", "url": listing["url"]}]
    ]
    if listing.get("id"):
        inline_keyboard[0].append({
            "text": "\u2B50 Spremi", 
            "callback_data": f"save_{listing['id']}"
        })

    success_count = 0
    for chat_id in chat_ids:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
            "reply_markup": {"inline_keyboard": inline_keyboard}
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            success_count += 1
        except Exception as e:
            logging.error(f"\u274c Failed to send notification to chat {chat_id}: {e}")

    return success_count > 0