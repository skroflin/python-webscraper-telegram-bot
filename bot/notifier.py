import asyncio
import logging
import time
from typing import Any, Dict, Optional, Union
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden, RetryAfter, TelegramError
from telegram.ext import Application

from analytics.feature_extractor import format_feature_badges
from analytics.match_scorer import calculate_match_score, get_match_badge
from analytics.poi import format_poi_distances, get_all_pois_from_db
from analytics.user_settings import get_all_users_with_preferences
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


class TelegramRateLimiter:
    """
    Asynchronous token bucket / interval rate limiter for Telegram Bot API:
    - Global throttle: Maximum ~20 messages/second (Telegram's limit is ~30/s).
    - Per-chat throttle: Minimum 0.5s interval per specific chat (Telegram's limit is ~1/s).
    """

    def __init__(self, global_limit_per_second: float = 20.0, per_chat_limit_seconds: float = 0.5):
        self.min_global_interval = 1.0 / max(1.0, global_limit_per_second)
        self.per_chat_limit = per_chat_limit_seconds
        self._last_global_send = 0.0
        self._last_chat_send: Dict[int, float] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, chat_id: int) -> None:
        async with self._lock:
            now = time.monotonic()

            elapsed_global = now - self._last_global_send
            if elapsed_global < self.min_global_interval:
                await asyncio.sleep(self.min_global_interval - elapsed_global)

            now = time.monotonic()
            last_chat = self._last_chat_send.get(chat_id, 0.0)
            elapsed_chat = now - last_chat
            if elapsed_chat < self.per_chat_limit:
                await asyncio.sleep(self.per_chat_limit - elapsed_chat)

            now = time.monotonic()
            self._last_global_send = now
            self._last_chat_send[chat_id] = now


rate_limiter = TelegramRateLimiter(global_limit_per_second=20.0, per_chat_limit_seconds=0.5)

_last_admin_alerts: Dict[str, float] = {}


def _resolve_bot(bot_or_app: Optional[Union[Application, Bot, Any]]) -> Optional[Bot]:
    """Helper to extract a Bot instance from Application, Bot or create one from token."""
    if bot_or_app is not None:
        if hasattr(bot_or_app, "bot"):
            return bot_or_app.bot
        return bot_or_app

    if TELEGRAM_BOT_TOKEN:
        try:
            return Bot(token=TELEGRAM_BOT_TOKEN)
        except Exception as e:
            logging.error(f"\U0000274c Could not initialize Telegram Bot from token: {e}")
            return None
    return None


async def send_message_rate_limited(
    bot: Any,
    chat_id: int,
    text: str,
    parse_mode: str = "Markdown",
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    max_retries: int = 3,
) -> bool:
    """
    Sends a message via Telegram Bot with rate limiting and automatic RetryAfter backoff.
    """
    if bot is None:
        logging.warning("Cannot send Telegram message: Bot is not configured.")
        return False

    for attempt in range(1, max_retries + 1):
        try:
            await rate_limiter.acquire(chat_id)
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
            return True

        except RetryAfter as e:
            sleep_time = float(e.retry_after) + 0.5
            logging.warning(
                f"\U000026A0 Telegram Rate Limit (HTTP 429) reached. Waiting {sleep_time:.2f}s (attempt {attempt}/{max_retries})..."
            )
            await asyncio.sleep(sleep_time)

        except Forbidden:
            logging.warning(f"\U0001F512 User {chat_id} has blocked the bot or chat is not accessible. Notification skipped.")
            return False

        except TelegramError as e:
            logging.error(f"\U0000274c Telegram API error sending to {chat_id} (attempt {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                await asyncio.sleep(1.0 * attempt)
            else:
                return False

        except Exception as e:
            logging.exception(f"\U0000274c Unexpected error sending to {chat_id}: {e}")
            return False

    return False


async def send_admin_alert(
    text: str,
    alert_key: Optional[str] = None,
    cooldown_seconds: int = 21600,
    bot_or_app: Optional[Any] = None,
) -> bool:
    """
    Sends an operational alert message to the bot administrator (TELEGRAM_CHAT_ID).
    Includes cooldown to prevent repetitive notification spam.
    """
    if not TELEGRAM_CHAT_ID:
        logging.info("\U0001F194 TELEGRAM_CHAT_ID not configured; skipping admin alert: %s", text.splitlines()[0])
        return False

    now = time.monotonic()
    if alert_key:
        last_sent = _last_admin_alerts.get(alert_key, 0.0)
        if (now - last_sent) < cooldown_seconds:
            logging.debug("Admin alert for key '%s' throttled (cooldown %ds).", alert_key, cooldown_seconds)
            return False
        _last_admin_alerts[alert_key] = now

    bot = _resolve_bot(bot_or_app)
    if not bot:
        return False

    try:
        admin_chat_id = int(TELEGRAM_CHAT_ID)
    except ValueError:
        admin_chat_id = TELEGRAM_CHAT_ID

    logging.info("\U0001F4E2 Sending admin alert (key=%s) to chat_id=%s", alert_key, admin_chat_id)
    return await send_message_rate_limited(
        bot=bot,
        chat_id=admin_chat_id,
        text=text,
        parse_mode="Markdown",
    )


async def notify_users_about_listing(
    app: Optional[Any] = None,
    listing: Optional[dict] = None,
    event_type: str = "inserted",
    min_score_threshold: int = 70,
) -> None:
    """
    Evaluates new listings or price drops against all user preference profiles
    and dispatches rate-limited personalized Telegram notifications.
    """
    if not listing:
        return

    bot = _resolve_bot(app)
    if not bot:
        logging.warning("Skipping notifications: No valid Bot instance or TELEGRAM_BOT_TOKEN configured.")
        return

    users, pois = await asyncio.gather(
        asyncio.to_thread(get_all_users_with_preferences),
        asyncio.to_thread(get_all_pois_from_db),
    )
    if not users:
        return

    header = "\U0001F195 **Novi oglas u ponudi!**" if event_type == "inserted" else "\U0001F4C9 **Pad cijene oglasa!**"

    for user in users:
        user_profile = {
            "max_price": user.get("max_price"),
            "min_area": user.get("min_area"),
            "must_have_lift": user.get("must_have_lift", 0),
            "must_have_pet": user.get("must_have_pet", 0),
            "must_have_parking": user.get("must_have_parking", 0),
        }
        user_loc_ids = user.get("location_ids", [])

        from analytics.feature_extractor import extract_features

        features = extract_features(listing.get("title", ""), listing.get("description", ""))
        if user_profile["must_have_pet"] and features.get("pet_prohibited"):
            continue
        if user_profile["must_have_lift"] and features.get("elevator_negative"):
            continue

        score, reasons = calculate_match_score(listing, user_profile, user_loc_ids, pois)

        if score < min_score_threshold:
            continue

        match_str = f"{get_match_badge(score)}\n"
        neighborhood_str = (
            f"\U0001F30D Kvart: **{listing.get('neighborhood')}**\n" if listing.get("neighborhood") else ""
        )

        if event_type == "price_drop" and listing.get("old_price"):
            price_str = (
                f"\U0001F4B0 Cijena: ~~{listing['old_price']:.2f} €~~ ➡️ **{listing['price']:.2f} €**\n"
            )
        else:
            price_str = f"\U0001F4B0 Cijena: **{listing['price']:.2f} €**\n"

        area_str = f"\U0001F4D0 Površina: **{listing['area_sqm']} m²**\n" if listing.get("area_sqm") else ""
        badges = format_feature_badges(listing.get("title", ""), listing.get("description", ""))
        poi_str = format_poi_distances(listing.get("latitude"), listing.get("longitude"), pois)

        reasons_text = ""
        if reasons:
            reasons_text = "\n💡 **Zašto vam odgovara:**\n" + "\n".join([f"- {r}" for r in reasons[:3]]) + "\n\n"

        text = (
            f"{header}\n\n"
            f"\U0001F31F **{listing['title']}**\n\n"
            f"{match_str}"
            f"{neighborhood_str}"
            f"{price_str}"
            f"{area_str}\n"
            f"{badges}"
            f"{reasons_text}"
            f"{poi_str}"
        )

        keyboard = [
            [
                InlineKeyboardButton("Pogledaj oglas 🔗", url=listing["url"]),
                InlineKeyboardButton("⭐ Spremi", callback_data=f"save_{listing['id']}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        success = await send_message_rate_limited(
            bot=bot,
            chat_id=user["telegram_id"],
            text=text,
            reply_markup=reply_markup,
        )
        if success:
            logging.info(f"\U00002705 Sent notification to user {user['telegram_id']} (Match: {score}%)")
