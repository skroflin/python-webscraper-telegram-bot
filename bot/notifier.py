import asyncio
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application
from analytics.match_scorer import calculate_match_score, get_match_badge
from analytics.poi import format_poi_distances, get_all_pois_from_db
from analytics.feature_extractor import format_feature_badges
from analytics.user_settings import get_all_users_with_preferences


async def notify_users_about_listing(
    app: Application,
    listing: dict,
    event_type: str = "inserted",
    min_score_threshold: int = 70
) -> None:
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
        neighborhood_str = f"\U0001F30D Kvart: **{listing.get('neighborhood')}**\n" if listing.get("neighborhood") else ""

        if event_type == "price_drop" and listing.get("old_price"):
            price_str = f"\U0001F4B0 Cijena: ~~{listing['old_price']:.2f} €~~ \u27A1\ufe0f **{listing['price']:.2f} €**\n"
        else:
            price_str = f"\U0001F4B0 Cijena: **{listing['price']:.2f} €**\n"

        area_str = f"\U0001F4D0 Površina: **{listing['area_sqm']} m²**\n" if listing.get("area_sqm") else ""
        badges = format_feature_badges(listing.get("title", ""), listing.get("description", ""))
        poi_str = format_poi_distances(
            listing.get("latitude"), listing.get("longitude"), pois
        )

        reasons_text = ""
        if reasons:
            reasons_text = "\n\U0001F4A1 **Zašto vam odgovara:**\n" + "\n".join([f"- {r}" for r in reasons[:3]]) + "\n\n"

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

        keyboard = [[
            InlineKeyboardButton("Pogledaj oglas \U0001F517", url=listing["url"]),
            InlineKeyboardButton("\u2B50 Spremi", callback_data=f"save_{listing['id']}")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await app.bot.send_message(
                chat_id=user["telegram_id"],
                text=text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
            logging.info(f"\u2705 Sent notification to user {user['telegram_id']} (Match: {score}%)")
        except Exception as e:
            logging.error(f"\u274c Failed to send notification to user {user['telegram_id']}: {e}")