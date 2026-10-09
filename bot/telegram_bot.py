import asyncio
import logging
import sys
from pathlib import Path
from datetime import time as datetime_time
from telegram import (
    Update,
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.constants import ChatType
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from telegram.error import BadRequest

sys.path.append(str(Path(__file__).resolve().parent.parent))

from scrapers.health_check import run_health_check
from analytics.poi import format_poi_distances, get_all_pois_from_db
from database.database import init_db
from config import TELEGRAM_BOT_TOKEN, SCRAPE_INTERVAL_MINUTES
from main import run_pipeline
from analytics.market_stats import (
    get_market_analytics,
    get_best_buy_listings,
    get_latest_listings,
    get_listings_near_location,
    get_neighborhood_stats,
    get_listings_by_neighborhood,
)
from analytics.user_settings import (
    set_user_budget,
    set_user_min_area,
    get_user_profile,
    reset_user_filters,
    save_listing,
    remove_saved_listing,
    get_saved_listings,
    add_user_neighborhood,
    remove_user_neighborhood,
    get_user_neighborhoods,
    get_all_locations,
    get_user_location_ids,
    toggle_user_neighborhood_by_id,
    save_user_location,
    toggle_user_priority,
)
from analytics.charts import generate_neighborhood_price_chart
from analytics.feature_extractor import format_feature_badges
from analytics.match_scorer import calculate_match_score, get_match_badge

logging.basicConfig(level=logging.INFO)

async def scheduled_health_check_job(context: ContextTypes.DEFAULT_TYPE):
    logging.info("\U000023F0 Starting automatic daily Health Check of listings...")
    try:
        checked, deactivated = await asyncio.to_thread(run_health_check)
        logging.info(f"\U0001F9F9 Daily cleanup finished: {deactivated}/{checked} ads marked as inactive.")
    except Exception as e:
        logging.error(f"\U0000274C Error running Health Check task: {e}")

async def setup_bot_metadata(application):
    try:
        await application.bot.set_my_description(
            "\U0001F44B Dobrodošli u Osijek Stanovi Bot! \U0001F3E2\n\n"
            "Pratim ponudu najma stanova u Osijeku na Njuškalu i Index Oglasniku "
            "te šaljem trenutne obavijesti o novim oglasima i padovima cijena.\U0001F440\U0001F4B0\n\n"
            "\u2728 Mogućnosti:\n"
            "- filtriranje po budžetu, kvadraturi i kvartovima\n"
            "- preferencije: lift, pet-friendly, parking\n"
            "- pretraga stanova u vašoj blizini\n"
            "- analitika i grafički prikaz cijena po kvartovima\n\n"
            "Pritisnite `/start` za početak! \U0001F680"
        )
        await application.bot.set_my_short_description(
            "Praćenje i trenutne obavijesti za najam stanova u Osijeku."
        )
        commands = [
            BotCommand("start", "Početak i pregled opcija"),
            BotCommand("postavke", "Filteri i preferencije"),
            BotCommand("moj_profil", "Pregled aktivnih postavki"),
            BotCommand("najnovije", "Zadnjih 5 stanova"),
            BotCommand("best_buy", "Najpovoljniji stanovi po m\u00b2"),
            BotCommand("blizu", "Stanovi blizu lokacije"),
            BotCommand("spremljeno", "Spremljeni oglasi"),
            BotCommand("analitika", "Prosje\u010dne cijene najma"),
            BotCommand("graf", "Grafi\u010dka analiza kvartova"),
        ]
        await application.bot.set_my_commands(commands)
    except Exception as e:
        logging.warning(f"Could not update bot metadata: {e}")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "\U0001F44B **Bok! Ja sam tvoj Osijek Stanovi Bot.** \U0001F916\n\n"
        "\u2699\ufe0f **Korisnički filteri i postavke:**\n"
        "- `/postavke` - interaktivni izbornik za postavke i kvartove\n"
        "- `/postavi_budzet <cijena>` - postavi max cijenu (npr. `/postavi_budzet 400`)\n"
        "- `/postavi_kvadraturu <m2>` - postavi min površinu (npr. `/postavi_kvadraturu 35`)\n"
        "- `/moj_profil` - pregledaj trenutno aktivne filtere\n"
        "- `/ponisti_filtere` - uklanja sve filtere (primaš sve oglase)\n\n"
        "\U0001F4CA **Analitika i pretraga:**\n"
        "- `/analitika` - prosječne cijene i ukupna statistika\n"
        "- `/kvartovi` - pregled cijena po osječkim kvartovima\n"
        "- `/kvart <ime kvarta>` - pregled oglasa u kvartu (npr. `/kvart Retfala`)\n"
        "- `/best_buy` - najpovoljniji stanovi po m^2\n"
        "- `/najnovije` - zadnjih 5 stanova iz baze\n"
        "- `/blizu [km]` - pronađi stanove blizu svoje lokacije (zadano 3 km)\n"
        "- `/spremljeno` - vaši omiljeni/spremljeni oglasi \u2B50\n"
        "- `/graf` - grafička analiza cijena po kvartovima\n"
    )
    keyboard = [
        [
            InlineKeyboardButton("\u2699\ufe0f Otvori postavke", callback_data="cb_settings_main"),
            InlineKeyboardButton("\U0001F4CD Odaberi kvartove", callback_data="cb_settings_neighborhoods"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=reply_markup)


async def set_budget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("\u26A0\ufe0f Navedite iznos. Primjer: `/postavi_budzet 400`", parse_mode="Markdown")
        return

    try:
        price = float(context.args[0].replace(",", "."))
        if price <= 0:
            raise ValueError

        if set_user_budget(user.id, user.first_name, price):
            await update.message.reply_text(f"\u2705 Maksimalni budžet postavljen na **{price:.2f} €**.", parse_mode="Markdown")
        else:
            await update.message.reply_text("\u274c Greška pri spremanju budžeta u bazu.")
    except ValueError:
        await update.message.reply_text("\u274c Unesite valjani brojčani iznos (npr. `/postavi_budzet 450`).", parse_mode="Markdown")


async def set_area_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("\u26A0\ufe0f Navedite površinu. Primjer: `/postavi_kvadraturu 40`", parse_mode="Markdown")
        return

    try:
        area = float(context.args[0].replace(",", "."))
        if area <= 0:
            raise ValueError

        if set_user_min_area(user.id, user.first_name, area):
            await update.message.reply_text(f"\u2705 Minimalna kvadratura postavljena na **{area:.1f} m^2**.", parse_mode="Markdown")
        else:
            await update.message.reply_text("\u274c Greška pri spremanju kvadrature u bazu.")
    except ValueError:
        await update.message.reply_text("\u274c Unesite valjani broj (npr. `/postavi_kvadraturu 35`).", parse_mode="Markdown")


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    profile = await asyncio.to_thread(get_user_profile, user.id)
    neighborhoods = await asyncio.to_thread(get_user_neighborhoods, user.id)

    budget = f"**{profile['max_price']:.2f} €**" if profile and profile.get("max_price") else "Nije postavljen (svi oglasi)"
    area = f"**{profile['min_area']:.1f} m²**" if profile and profile.get("min_area") else "Nije postavljeno (sve kvadrature)"
    locs = ", ".join(neighborhoods) if neighborhoods else "Svi kvartovi (nema ograničenja)"

    lift = "\U00002705 Da" if profile and profile.get("must_have_lift") else "\U0000274c Isključeno"
    pet = "\U00002705 Da" if profile and profile.get("must_have_pet") else "\U0000274c Isključeno"
    parking = "\U00002705 Da" if profile and profile.get("must_have_parking") else "\U0000274c Isključeno"

    msg = (
        f"\U0001F464 **Moje postavke i filteri ({user.first_name})**\n\n"
        f"\U0001F4B0 Maksimalna cijena: {budget}\n"
        f"\U0001F4D0 Minimalna površina: {area}\n"
        f"\U0001F30D Kvartovi: **{locs}**\n"
        f"\U0001F6D7 Obavezno lift: {lift}\n"
        f"\U0001F436 Pet friendly: {pet}\n"
        f"\U0001F17F\ufe0f Obavezno parking: {parking}\n\n"
        "Promijenite filtere u interaktivnom izborniku `/postavke` ili naredbama:\n"
        "- `/postavi_budzet <cijena>`\n"
        "- `/postavi_kvadraturu <m2>`\n"
        "- `/ponisti_filtere` - Uklanja sve filtere"
    )

    await update.message.reply_text(msg, parse_mode="Markdown")


async def reset_filters_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if reset_user_filters(user.id):
        await update.message.reply_text("\U0001F504 Svi filteri su poništeni. Primat ćete sve oglase.", parse_mode="Markdown")
    else:
        await update.message.reply_text("\u274c Greška pri poništavanju filtera.")


async def saved_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    listings = await asyncio.to_thread(get_saved_listings, user.id)

    if not listings:
        await update.message.reply_text("\u2139\ufe0f Nemate spremljenih oglasa u omiljenima.", parse_mode="Markdown")
        return

    profile = await asyncio.to_thread(get_user_profile, user.id)
    user_loc_ids = await asyncio.to_thread(get_user_location_ids, user.id)
    pois = await asyncio.to_thread(get_all_pois_from_db)

    scored_listings = []
    for item in listings:
        score, reasons = calculate_match_score(item, profile, user_loc_ids, pois)
        item["match_score"] = score
        item["match_reasons"] = reasons
        scored_listings.append(item)

    scored_listings.sort(key=lambda x: x["match_score"], reverse=True)

    await update.message.reply_text(
        f"\u2B50 **Vaši spremljeni oglasi ({len(scored_listings)}), rangirani po vašim preferencijama:**", 
        parse_mode="Markdown"
    )

    for item in scored_listings:
        area = f"{item['area_sqm']} m²" if item.get("area_sqm") else "Nije navedeno"
        match_str = f"{get_match_badge(item['match_score'])}\n"
        neighborhood_str = f"\U0001F30D Kvart: **{item['neighborhood']}**\n" if item.get("neighborhood") else ""
        badges = format_feature_badges(item.get("title", ""), item.get("description", ""))
        poi_str = format_poi_distances(
            item.get("latitude"), item.get("longitude"), pois
        )

        reasons_text = ""
        if item.get("match_reasons"):
            reasons_text = "\n\U0001f4a1 **Zašto odgovara:**\n" + "\n".join([f"- {r}" for r in item["match_reasons"][:3]]) + "\n\n"

        text = (
            f"\U0001F31F **{item['title']}**\n\n"
            f"{match_str}"
            f"{neighborhood_str}"
            f"\U0001F4B0 Cijena: **{item['price']:.2f} €**\n"
            f"\U0001F4D0 Površina: **{area}**\n\n"
            f"{badges}"
            f"{reasons_text}"
            f"{poi_str}"
            f"\U0001F4CB Izvor: **{item['source_platform']}**\n"
        )
        keyboard = [[
            InlineKeyboardButton("Pogledaj oglas \U0001F517", url=item["url"]),
            InlineKeyboardButton("\U0001F5D1\ufe0f Ukloni", callback_data=f"unsave_{item['id']}")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)


async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data

    if data.startswith("save_"):
        listing_id = int(data.split("_")[1])
        if await asyncio.to_thread(save_listing, user.id, user.first_name, listing_id):
            await query.answer("\u2705 Oglas spremljen u omiljene!", show_alert=False)
        else:
            await query.answer("\u274c Greška pri spremanju oglasa.", show_alert=True)

    elif data.startswith("unsave_"):
        listing_id = int(data.split("_")[1])
        if await asyncio.to_thread(remove_saved_listing, user.id, listing_id):
            await query.answer("\U0001F5D1\ufe0f Oglas uklonjen iz spremljenih!", show_alert=False)
            try:
                await query.edit_message_text(
                    f"~~{query.message.text}~~\n\n_\U0001F5D1\ufe0f Uklonjeno iz omiljenih._",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        else:
            await query.answer("\u274c Greška pri uklanjanju oglasa.", show_alert=True)


async def latest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    listings = await asyncio.to_thread(get_latest_listings, 5)

    if not listings:
        await update.message.reply_text("\u2139\ufe0f Trenutno nema unesenih stanova u bazi.")
        return

    await update.message.reply_text("\U0001F4CB **Zadnjih 5 stanova u bazi:**", parse_mode="Markdown")

    for item in listings:
        area = f"{item['area_sqm']} m^2" if item.get("area_sqm") else "Nije navedeno"
        badges = format_feature_badges(item.get("title", ""), item.get("description", ""))
        text = (
            f"\U0001F31F **{item['title']}**\n\n"
            f"\U0001F4B0 cijena: **{item['price']:.2f} €**\n"
            f"\U0001F4D0 površina: **{area}**\n"
            f"{badges}"
            f"\U0001F4CB izvor: **{item['source_platform']}**\n"
        )
        keyboard = [[
            InlineKeyboardButton("Pogledaj oglas \U0001F517", url=item["url"]),
            InlineKeyboardButton("\u2B50 Spremi", callback_data=f"save_{item['id']}")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await send_listing_item(update, text, item, reply_markup)


async def nearby_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != ChatType.PRIVATE:
        await update.message.reply_text("Pretraga lokacije dostupna je u privatnom razgovoru s botom.")
        return

    radius_km = 3.0
    if context.args:
        try:
            radius_km = float(context.args[0].replace(",", "."))
            if not 0 < radius_km <= 50:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "Radijus mora biti broj veći od 0 i najviše 50 km. Primjer: `/blizu 2.5`",
                parse_mode="Markdown",
            )
            return

    context.user_data["nearby_radius_km"] = radius_km
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("Pošalji trenutnu lokaciju", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await update.message.reply_text(
        f"Pošaljite svoju lokaciju za pretragu aktivnih oglasa u radijusu {radius_km:g} km. "
        "Dijeljenjem lokacije sprema se vaša zadnja lokacija u profilu.",
        reply_markup=keyboard,
    )


async def location_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    location = message.location
    radius_km = context.user_data.pop("nearby_radius_km", 3.0)
    user = update.effective_user
    await asyncio.to_thread(save_user_location, user.id, user.first_name or "", location.latitude, location.longitude)

    listings = await asyncio.to_thread(get_listings_near_location, location.latitude, location.longitude, radius_km)
    await message.reply_text(
        f"\U0001F4CD Oglasi unutar {radius_km:g} km, rangirani po udaljenosti od centra kvarta:",
        reply_markup=ReplyKeyboardRemove(),
    )
    if not listings:
        await message.reply_text("U tom radijusu nema aktivnih oglasa s poznatom lokacijom.")
        return

    for item in listings:
        area = f"{item['area_sqm']} m²" if item.get("area_sqm") else "Nije navedeno"
        distance = item["distance_km"]
        distance_text = f"{distance * 1000:.0f} m" if distance < 1 else f"{distance:.1f} km"
        neighborhood = f"\U0001F30D Kvart: **{item['neighborhood']}**\n" if item.get("neighborhood") else ""
        text = (
            f"\U0001F31F **{item['title']}**\n\n"
            f"\U0001F4CD Od centra kvarta: **{distance_text}**\n"
            f"{neighborhood}"
            f"\U0001F4B0 Cijena: **{item['price']:.2f} €**\n"
            f"\U0001F4D0 Površina: **{area}**\n"
            f"\U0001F4CB Izvor: **{item['source_platform']}**\n"
        )
        buttons = [InlineKeyboardButton("Pogledaj oglas \U0001F517", url=item["url"])]
        buttons.append(InlineKeyboardButton("\u2B50 Spremi", callback_data=f"save_{item['id']}"))
        if item.get("latitude") is not None and item.get("longitude") is not None:
            buttons.append(InlineKeyboardButton(
                "Karta kvarta \U0001F4CD",
                url=f"https://www.google.com/maps?q={item['latitude']},{item['longitude']}",
            ))
        await send_listing_item(update, text, item, InlineKeyboardMarkup([buttons]))


async def analytics_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = await asyncio.to_thread(get_market_analytics)

    if not stats or not stats.get("total"):
        await update.message.reply_text("\u2139\ufe0f Baza je prazna ili nema podataka za analitiku.")
        return

    msg = (
        "\U0001F4CA **Analitika tržišta najma u Osijeku**\n\n"
        f"- ukupno stanova u bazi: **{stats['total']}**\n"
        f"- prosječna mjesečna najamnina: **{stats['avg_price']:.2f} €**\n"
        f"- prosječna cijena po m^2: **{stats['avg_sqm_price']:.2f} €/m^2**"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def neighborhoods_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = await asyncio.to_thread(get_neighborhood_stats)

    if not stats:
        await update.message.reply_text("\u2139\ufe0f Trenutno nema oglasa s dodijeljenim kvartovima u bazi.")
        return

    msg_text = "\U0001F4CD **Prosječne cijene najma po kvartovima:**\n\n"

    for item in stats:
        avg_price = item["avg_price"]
        avg_sqm = item["avg_sqm_price"]
        sqm_text = f"{avg_sqm:.2f} €/m^2" if avg_sqm else "N/A"

        msg_text += (
            f"\U0001F4B0\U0001F4B8 **{item['neighborhood']}** ({item['total_listings']} oglasa)\n"
            f"- prosječna cijena: **{avg_price:.2f} €**\n"
            f"- cijena po m^2: **{sqm_text}**\n\n"
        )

    await update.message.reply_text(msg_text, parse_mode="Markdown")


async def best_buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    profile = await asyncio.to_thread(get_user_profile, user.id)
    user_loc_ids = await asyncio.to_thread(get_user_location_ids, user.id)
    pois = await asyncio.to_thread(get_all_pois_from_db)

    listings = await asyncio.to_thread(get_best_buy_listings, 5)

    if not listings:
        await update.message.reply_text("\u2139\ufe0f Nema dovoljno podataka za izračun.")
        return

    scored_listings = []
    for item in listings:
        score, reasons = calculate_match_score(item, profile, user_loc_ids, pois)
        item["match_score"] = score
        item["match_reasons"] = reasons
        scored_listings.append(item)

    scored_listings.sort(key=lambda x: x["match_score"], reverse=True)

    await update.message.reply_text("\U0001F31F **Top prilike prilagođene vašim preferencijama:**", parse_mode="Markdown")

    for item in scored_listings[:3]:
        match_str = f"{get_match_badge(item['match_score'])}\n"
        neighborhood_str = f"\U0001F30D Kvart: **{item['neighborhood']}**\n" if item.get("neighborhood") else ""
        poi_str = format_poi_distances(
            item.get("latitude"), item.get("longitude"), pois
        )
        badges = format_feature_badges(item.get("title", ""), item.get("description", ""))

        reasons_text = ""
        if item.get("match_reasons"):
            reasons_text = "\n\U0001f4a1 **Zašto odgovara:**\n" + "\n".join([f"- {r}" for r in item["match_reasons"][:3]]) + "\n\n"

        text = (
            f"\U0001F31F **{item['title']}**\n\n"
            f"{match_str}"
            f"{neighborhood_str}"
            f"\U0001F4B0 Cijena: **{item['price']:.2f} €** ({item['price_per_sqm']:.2f} €/m^2)\n"
            f"\U0001F4D0 Površina: **{item['area_sqm']} m^2**\n\n"
            f"{badges}"
            f"{reasons_text}"
            f"{poi_str}"
        )
        keyboard = [[
            InlineKeyboardButton("Pogledaj priliku \U0001F517", url=item["url"]),
            InlineKeyboardButton("\u2B50 Spremi", callback_data=f"save_{item['id']}")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)


async def neighborhood_listings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "\u26A0\ufe0f Navedite naziv kvarta. Primjer: `/kvart Retfala` ili `/kvart Centar`",
            parse_mode="Markdown"
        )
        return

    neighborhood_name = " ".join(context.args)
    listings = await asyncio.to_thread(get_listings_by_neighborhood, neighborhood_name, 5)

    if not listings:
        await update.message.reply_text(
            f"\u2139\ufe0f Trenutno nema aktivnih oglasa za kvart **{neighborhood_name}**.",
            parse_mode="Markdown"
        )
        return

    exact_name = listings[0]["neighborhood"]
    await update.message.reply_text(
        f"\U0001F3E0 **Zadnji oglasi za kvart {exact_name}:**",
        parse_mode="Markdown"
    )

    for item in listings:
        area = f"{item['area_sqm']} m^2" if item.get("area_sqm") else "Nije navedeno"
        text = (
            f"\U0001F31F **{item['title']}**\n\n"
            f"\U0001F4B0 cijena: **{item['price']:.2f} €**\n"
            f"\U0001F4D0 površina: **{area}**\n"
            f"\U0001F4CB izvor: **{item['source_platform']}**\n"
        )
        keyboard = [[InlineKeyboardButton("Pogledaj oglas \U0001F517", url=item["url"])]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)


async def send_listing_item(update: Update, text: str, item: dict, reply_markup: InlineKeyboardMarkup):
    image_url = item.get("image_url")
    if image_url:
        try:
            await update.message.reply_photo(
                photo=image_url,
                caption=text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
            return
        except Exception as e:
            logging.warning(f"Failed to send photo for listing {item.get('id')}: {e}")

    await update.message.reply_text(
        text=text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )


async def add_neighborhood_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text(
            "\U000026A0 Navedite naziv kvarta. Primjer: `/dodaj_kvart Retfala`",
            parse_mode="Markdown"
        )
        return

    neighborhood_name = " ".join(context.args)
    success, message = await asyncio.to_thread(add_user_neighborhood, user.id, user.first_name, neighborhood_name)

    if success:
        await update.message.reply_text(
            f"\U00002705 Kvart **{message}** je dodan na vašu listu praćenja!\n"
            f"Sada ćete primati obavijesti samo za vaše odabrane kvartove.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(f"\U0000274c {message}", parse_mode="Markdown")


async def remove_neighborhood_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text(
            "\U000026A0 Navedite naziv kvarta. Primjer: `/ukloni_kvart Retfala`",
            parse_mode="Markdown"
        )
        return

    neighborhood_name = " ".join(context.args)
    success, message = await asyncio.to_thread(remove_user_neighborhood, user.id, neighborhood_name)

    if success:
        await update.message.reply_text(
            f"\U0001F5D1\ufe0f Kvart **{message}** je uklonjen s vaše liste praćenja.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(f"\U0000274c {message}", parse_mode="Markdown")


async def my_neighborhoods_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    neighborhoods = await asyncio.to_thread(get_user_neighborhoods, user.id)

    if not neighborhoods:
        await update.message.reply_text(
            "\U0001F4CD **Nemate postavljenih kvartova za filtriranje.**\n"
            "Primate obavijesti za sve dijelove grada Osijeka.\n\n"
            "Dodajte kvart naredbom: `/dodaj_kvart Retfala` ili u `/postavke`.",
            parse_mode="Markdown"
        )
        return

    list_text = "\n".join([f"• **{name}**" for name in neighborhoods])
    msg = (
        f"\U0001F4CD **Vaši odabrani kvartovi za obavijesti ({len(neighborhoods)}):**\n\n"
        f"{list_text}\n\n"
        "Upravljanje:\n"
        "- `/dodaj_kvart <naziv>` - dodaj novi kvart\n"
        "- `/ukloni_kvart <naziv>` - ukloni kvart\n"
        "- `/postavke` - otvori interaktivne postavke"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def scheduled_scrape_job(context: ContextTypes.DEFAULT_TYPE):
    logging.info("\u23f1\ufe0f Pokretanje automatskog pozadinskog skrepanja...")
    try:
        stats = await run_pipeline(app=context.application, max_pages=3)
        logging.info("Scheduled scrape completed: %s", stats)
    except Exception as e:
        logging.error(f"\u274c Greška pri izvođenju zakazanog skrepanja: {e}")


async def graph_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("\U0001F4CA Generiram grafičku analitiku...")

    buf = await asyncio.to_thread(generate_neighborhood_price_chart)
    if not buf:
        await update.message.reply_text("\U00002139 Nema dovoljno podataka o kvartovima i m^2 za izradu grafa.")
        return

    await update.message.reply_photo(
        photo=buf,
        caption="\U0001F4C8 **Analitika tržišta najma po osječkim kvartovima (EUR / m^2)**",
        parse_mode="Markdown"
    )


def format_settings_text(telegram_id: int) -> str:
    profile = get_user_profile(telegram_id) or {}
    neighborhoods = get_user_neighborhoods(telegram_id)

    budget_str = f"{profile['max_price']:.2f} €" if profile and profile.get("max_price") else "Nije postavljen"
    area_str = f"{profile['min_area']:.1f} m²" if profile and profile.get("min_area") else "Nije postavljeno"
    loc_str = ", ".join(neighborhoods) if neighborhoods else "Svi kvartovi (nema ograničenja)"

    lift_str = "\U00002705 Obavezno" if profile.get("must_have_lift") else "\U0000274c Nije obavezno"
    pet_str = "\U00002705 Obavezno" if profile.get("must_have_pet") else "\U0000274c Nije obavezno"
    parking_str = "\U00002705 Obavezno" if profile.get("must_have_parking") else "\U0000274c Nije obavezno"

    return (
        f"\u2699\ufe0f **Korisnički filteri i postavke**\n\n"
        f"- \U0001f4b0 Maksimalni budžet: **{budget_str}**\n"
        f"- \U0001f4d0 Minimalna kvadratura: **{area_str}**\n"
        f"- \U0001f30d Kvartovi: **{loc_str}**\n"
        f"- \U0001f6d7 Zgrada s liftom: **{lift_str}**\n"
        f"- \U0001f436 Pet friendly: **{pet_str}**\n"
        f"- \U0001f17f\ufe0f Parking / garaža: **{parking_str}**\n\n"
        f"Dodirnite opciju ispod za uključivanje/isključivanje prioriteta ili promjenu filtera:"
    )


def build_main_settings_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    profile = get_user_profile(telegram_id) or {}
    lift_val = profile.get("must_have_lift", 0) == 1
    pet_val = profile.get("must_have_pet", 0) == 1
    parking_val = profile.get("must_have_parking", 0) == 1

    lift_btn = f"\U0001f6d7 Lift: {'\U00002705 DA' if lift_val else '\U0000274c NE'}"
    pet_btn = f"\U0001f436 Ljubimci: {'\U00002705 DA' if pet_val else '\U0000274c NE'}"
    parking_btn = f"\U0001f17f\ufe0f Parking: {'\U00002705 DA' if parking_val else '\U0000274c NE'}"

    keyboard = [
        [
            InlineKeyboardButton("\U0001f4b0 Postavi budžet", callback_data="cb_settings_budget"),
            InlineKeyboardButton("\U0001f4d0 Min. kvadratura", callback_data="cb_settings_area"),
        ],
        [
            InlineKeyboardButton("\U0001f4cd Moji kvartovi", callback_data="cb_settings_neighborhoods"),
        ],
        [
            InlineKeyboardButton(lift_btn, callback_data="cb_toggle_lift"),
            InlineKeyboardButton(pet_btn, callback_data="cb_toggle_pet"),
        ],
        [
            InlineKeyboardButton(parking_btn, callback_data="cb_toggle_parking"),
            InlineKeyboardButton("\U0001f504 Resetiraj filtere", callback_data="cb_settings_reset"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_neighborhoods_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    """Building interactive keyboard for selecting neighborhoods with checkmarks."""
    locations = get_all_locations()
    selected_ids = get_user_location_ids(telegram_id)

    keyboard = []
    row = []

    for loc in locations:
        loc_id = loc["id"]
        loc_name = loc["name"]

        if loc_id in selected_ids:
            prefix = "\u2705 "
        else:
            prefix = "\u274c "

        button_text = f"{prefix}{loc_name}"
        callback_data = f"cb_toggle_loc_{loc_id}"

        row.append(InlineKeyboardButton(button_text, callback_data=callback_data))

        if len(row) == 2:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    keyboard.append([
        InlineKeyboardButton("\u2b05\ufe0f Nazad u postavke", callback_data="cb_settings_main")
    ])

    return InlineKeyboardMarkup(keyboard)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /postavke command."""
    user = update.effective_user
    await update.message.reply_text(
        format_settings_text(user.id),
        reply_markup=build_main_settings_keyboard(user.id),
        parse_mode="Markdown"
    )


async def settings_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Central handler for inline button interactions in settings."""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    data = query.data

    if data == "cb_settings_main":
        await query.edit_message_text(
            format_settings_text(user.id),
            reply_markup=build_main_settings_keyboard(user.id),
            parse_mode="Markdown"
        )

    elif data in ("cb_toggle_lift", "cb_toggle_pet", "cb_toggle_parking"):
        key_map = {
            "cb_toggle_lift": "must_have_lift",
            "cb_toggle_pet": "must_have_pet",
            "cb_toggle_parking": "must_have_parking",
        }
        key = key_map[data]
        toggle_user_priority(user.id, key, user.first_name or "")
        try:
            await query.edit_message_text(
                format_settings_text(user.id),
                reply_markup=build_main_settings_keyboard(user.id),
                parse_mode="Markdown"
            )
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise e

    elif data == "cb_settings_neighborhoods":
        locations = get_all_locations()
        if not locations:
            msg = (
                f"\U0001f4cd **Odabir kvartova za praćenje**\n\n"
                f"\u2139\ufe0f U bazi podataka trenutno nema unesenih kvartova u tablici `locations`.\n"
                f"Pokrenite skrepanje (`main.py`) kako bi se baza napunila kvartovima."
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("\u2b05\ufe0f Nazad u postavke", callback_data="cb_settings_main")]
            ])
            await query.edit_message_text(msg, reply_markup=keyboard, parse_mode="Markdown")
            return

        status_note = (
            "Primate obavijesti samo za **označene kvartove (\u2705)**.\n"
            "Ako nijedan kvart nije označen, primate obavijesti za sve kvartove."
        )
        msg = (
            f"\U0001f4cd **Odabir kvartova za praćenje**\n\n"
            f"{status_note}\n\n"
            f"Kliknite na kvart za uključivanje/isključivanje:"
        )
        await query.edit_message_text(
            msg,
            reply_markup=build_neighborhoods_keyboard(user.id),
            parse_mode="Markdown"
        )

    elif data.startswith("cb_toggle_loc_"):
        loc_id = int(data.replace("cb_toggle_loc_", ""))
        toggle_user_neighborhood_by_id(user.id, loc_id, user.first_name or "")

        try:
            await query.edit_message_reply_markup(
                reply_markup=build_neighborhoods_keyboard(user.id)
            )
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise e

    elif data == "cb_settings_budget":
        msg = (
            f"\U0001f4b0 **Postavljanje budžeta**\n\n"
            f"Za postavljanje maksimalnog iznosa najma pošaljite poruku u chatu u formatu:\n"
            f"`/postavi_budzet <iznos>`\n\n"
            f"Primjer: `/postavi_budzet 450`"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("\u2b05\ufe0f Nazad u postavke", callback_data="cb_settings_main")]
        ])
        await query.edit_message_text(msg, reply_markup=keyboard, parse_mode="Markdown")

    elif data == "cb_settings_area":
        msg = (
            f"\U0001f4d0 **Postavljanje minimalne kvadrature**\n\n"
            f"Za postavljanje minimalne stambene površine pošaljite poruku u chatu u formatu:\n"
            f"`/postavi_kvadraturu <m2>`\n\n"
            f"Primjer: `/postavi_kvadraturu 40`"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("\u2b05\ufe0f Nazad u postavke", callback_data="cb_settings_main")]
        ])
        await query.edit_message_text(msg, reply_markup=keyboard, parse_mode="Markdown")

    elif data == "cb_settings_reset":
        reset_user_filters(user.id)
        try:
            await query.edit_message_text(
                format_settings_text(user.id),
                reply_markup=build_main_settings_keyboard(user.id),
                parse_mode="Markdown"
            )
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise e


def run_bot_listener():
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is required to start the bot.")

    init_db()
    app = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(setup_bot_metadata)
        .build()
    )
    if app.job_queue is None:
        raise RuntimeError("python-telegram-bot JobQueue is unavailable; install its job-queue extra.")

    app.job_queue.run_repeating(
        scheduled_scrape_job,
        interval=SCRAPE_INTERVAL_MINUTES * 60,
        first=5,
        name="apartment_scrape",
        job_kwargs={"max_instances": 1, "coalesce": True},
    )
    app.job_queue.run_daily(
        scheduled_health_check_job,
        time=datetime_time(hour=3),
        name="listing_health_check",
    )
    logging.info(
        "\U000023F3 PTB JobQueue active: scraping every %s minutes.",
        SCRAPE_INTERVAL_MINUTES,
    )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("postavke", settings_command))
    app.add_handler(CommandHandler("postavi_budzet", set_budget_command))
    app.add_handler(CommandHandler("postavi_kvadraturu", set_area_command))
    app.add_handler(CommandHandler("moj_profil", profile_command))
    app.add_handler(CommandHandler("ponisti_filtere", reset_filters_command))

    app.add_handler(CommandHandler("analitika", analytics_command))
    app.add_handler(CommandHandler("kvartovi", neighborhoods_command))
    app.add_handler(CommandHandler("best_buy", best_buy_command))
    app.add_handler(CommandHandler("najnovije", latest_command))
    app.add_handler(CommandHandler("blizu", nearby_command))
    app.add_handler(CommandHandler("kvart", neighborhood_listings_command))
    app.add_handler(CommandHandler("spremljeno", saved_command))
    app.add_handler(CommandHandler("dodaj_kvart", add_neighborhood_command))
    app.add_handler(CommandHandler("ukloni_kvart", remove_neighborhood_command))
    app.add_handler(CommandHandler("moji_kvartovi", my_neighborhoods_command))
    app.add_handler(CommandHandler("graf", graph_command))

    app.add_handler(CallbackQueryHandler(button_callback_handler, pattern="^(save|unsave)_"))
    app.add_handler(CallbackQueryHandler(settings_callback_handler, pattern="^cb_"))
    app.add_handler(MessageHandler(filters.LOCATION, location_message_handler))

    logging.info("\U0001F916 Bot sluša vaše komande u Telegramu...")
    app.run_polling()


if __name__ == "__main__":
    run_bot_listener()