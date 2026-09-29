import logging
import sys
from pathlib import Path
from apscheduler.schedulers.background import BackgroundScheduler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)

sys.path.append(str(Path(__file__).resolve().parent.parent))

from config import TELEGRAM_BOT_TOKEN
from main import run_pipeline
from analytics.market_stats import (
    get_market_analytics,
    get_best_buy_listings,
    get_latest_listings,
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
)

logging.basicConfig(level=logging.INFO)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "\U0001F44B **Bok! Ja sam tvoj Osijek Stanovi Bot.**\n\n"
        "\u2699\ufe0f **Korisnički filteri za obavijesti:**\n"
        "- `/postavi_budzet <cijena>` - postavi max cijenu (npr. `/postavi_budzet 400`)\n"
        "- `/postavi_kvadraturu <m2>` - postavi min površinu (npr. `/postavi_kvadraturu 35`)\n"
        "- `/moj_profil` - pregledaj trenutno aktivne filtere\n"
        "- `/ponisti_filtere` - uklanja sve filtere (primaš sve oglase)\n\n"
        "\U0001F4CA **Analitika i pretraga:**\n"
        "- `/analitika` - prosječne cijene i ukupna statistika\n"
        "- `/kvartovi` - pregled cijena po osječkim kvartovima\n"
        "- `/kvart <ime kvarta>` - pregled oglasa u kvartu (npr. `/kvart Retfala`)\n"
        "- `/best_buy` - najpovoljniji stanovi po m²\n"
        "- `/najnovije` - zadnjih 5 stanova iz baze\n"
        "- `/spremljeno` - vaši omiljeni/spremljeni oglasi \u2B50"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


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
            await update.message.reply_text(f"\u2705 Minimalna kvadratura postavljena na **{area:.1f} m²**.", parse_mode="Markdown")
        else:
            await update.message.reply_text("\u274c Greška pri spremanju kvadrature u bazu.")
    except ValueError:
        await update.message.reply_text("\u274c Unesite valjani broj (npr. `/postavi_kvadraturu 35`).", parse_mode="Markdown")


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    profile = get_user_profile(user.id)

    if not profile:
        msg = (
            f"\U0001F464 **Profil: {user.first_name}**\n\n"
            "Trenutno nemate postavljene filtere. Bot vam šalje sve oglase.\n\n"
            "Postavite filtere naredbama:\n"
            "- `/postavi_budzet <cijena>`\n"
            "- `/postavi_kvadraturu <m2>`"
        )
    else:
        budget = f"**{profile['max_price']:.2f} €**" if profile.get("max_price") else "Nije postavljen (svi oglasi)"
        area = f"**{profile['min_area']:.1f} m²**" if profile.get("min_area") else "Nije postavljeno (sve kvadrature)"
        msg = (
            f"\U0001F464 **Moje postavke obavijesti ({user.first_name})**\n\n"
            f"\U0001F4B0 Maksimalna cijena: {budget}\n"
            f"\U0001F4D0 Minimalna površina: {area}\n\n"
            "Promijenite filtere:\n"
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
    listings = get_saved_listings(user.id)

    if not listings:
        await update.message.reply_text("\u2139\ufe0f Nemate spremljenih oglasa u omiljenima.", parse_mode="Markdown")
        return

    await update.message.reply_text(f"\u2B50 **Vaši spremljeni oglasi ({len(listings)}):**", parse_mode="Markdown")

    for item in listings:
        area = f"{item['area_sqm']} m²" if item.get("area_sqm") else "Nije navedeno"
        text = (
            f"\U0001F31F **{item['title']}**\n\n"
            f"\U0001F4B0 cijena: **{item['price']:.2f} €**\n"
            f"\U0001F4D0 površina: **{area}**\n"
            f"\U0001F4CB izvor: **{item['source_platform']}**\n"
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
        if save_listing(user.id, user.first_name, listing_id):
            await query.answer("\u2705 Oglas spremljen u omiljene!", show_alert=False)
        else:
            await query.answer("\u274c Greška pri spremanju oglasa.", show_alert=True)

    elif data.startswith("unsave_"):
        listing_id = int(data.split("_")[1])
        if remove_saved_listing(user.id, listing_id):
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
    listings = get_latest_listings(limit=5)

    if not listings:
        await update.message.reply_text("\u2139\ufe0f Trenutno nema unesenih stanova u bazi.")
        return

    await update.message.reply_text("\U0001F4CB **Zadnjih 5 stanova u bazi:**", parse_mode="Markdown")

    for item in listings:
        area = f"{item['area_sqm']} m²" if item.get("area_sqm") else "Nije navedeno"
        text = (
            f"\U0001F31F **{item['title']}**\n\n"
            f"\U0001F4B0 cijena: **{item['price']:.2f} €**\n"
            f"\U0001F4D0 površina: **{area}**\n"
            f"\U0001F4CB izvor: **{item['source_platform']}**\n"
        )
        keyboard = [[
            InlineKeyboardButton("Pogledaj oglas \U0001F517", url=item["url"]),
            InlineKeyboardButton("\u2B50 Spremi", callback_data=f"save_{item['id']}")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)


async def analytics_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = get_market_analytics()

    if not stats or not stats.get("total"):
        await update.message.reply_text("\u2139\ufe0f Baza je prazna ili nema podataka za analitiku.")
        return

    msg = (
        "\U0001F4CA **Analitika tržišta najma u Osijeku**\n\n"
        f"- ukupno stanova u bazi: **{stats['total']}**\n"
        f"- prosječna mjesečna najamnina: **{stats['avg_price']:.2f} €**\n"
        f"- prosječna cijena po m²: **{stats['avg_sqm_price']:.2f} €/m²**"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def neighborhoods_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = get_neighborhood_stats()

    if not stats:
        await update.message.reply_text("\u2139\ufe0f Trenutno nema oglasa s dodijeljenim kvartovima u bazi.")
        return

    msg_text = "\U0001F4CD **Prosječne cijene najma po kvartovima:**\n\n"

    for item in stats:
        avg_price = item["avg_price"]
        avg_sqm = item["avg_sqm_price"]
        sqm_text = f"{avg_sqm:.2f} €/m²" if avg_sqm else "N/A"

        msg_text += (
            f"\U0001F4B0\U0001F4B8 **{item['neighborhood']}** ({item['total_listings']} oglasa)\n"
            f"- prosječna cijena: **{avg_price:.2f} €**\n"
            f"- cijena po m²: **{sqm_text}**\n\n"
        )

    await update.message.reply_text(msg_text, parse_mode="Markdown")


async def best_buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    listings = get_best_buy_listings(limit=3)

    if not listings:
        await update.message.reply_text("\u2139\ufe0f Nema dovoljno podataka o kvadraturama za izračun.")
        return

    await update.message.reply_text("\U0001F31F **Top 3 najpovoljnija stana po m²:**", parse_mode="Markdown")

    for item in listings:
        text = (
            f"\U0001F31F **{item['title']}**\n\n"
            f"\U0001F4B0 Cijena: **{item['price']:.2f} €** ({item['price_per_sqm']:.2f} €/m²)\n"
            f"\U0001F4D0 Površina: **{item['area_sqm']} m²**\n"
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
    listings = get_listings_by_neighborhood(neighborhood_name, limit=5)

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
        area = f"{item['area_sqm']} m²" if item.get("area_sqm") else "Nije navedeno"
        text = (
            f"\U0001F31F **{item['title']}**\n\n"
            f"\U0001F4B0 cijena: **{item['price']:.2f} €**\n"
            f"\U0001F4D0 površina: **{area}**\n"
            f"\U0001F4CB izvor: **{item['source_platform']}**\n"
        )
        keyboard = [[InlineKeyboardButton("Pogledaj oglas \U0001F517", url=item["url"])]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)


def scheduled_scrape_job():
    logging.info("\u23f1\ufe0f Pokretanje automatskog pozadinskog skrepanja...")
    try:
        run_pipeline(max_pages=3)
    except Exception as e:
        logging.error(f"\u274c Greška pri izvođenju zakazanog skrepanja: {e}")


def run_bot_listener():
    scheduler = BackgroundScheduler()
    scheduler.add_job(scheduled_scrape_job, 'interval', minutes=20)
    scheduler.start()
    logging.info("\U000023F3 Pozadinski raspoređivač (APScheduler) aktivan: scrape-anje zakazano svakih 20 min.")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("postavi_budzet", set_budget_command))
    app.add_handler(CommandHandler("postavi_kvadraturu", set_area_command))
    app.add_handler(CommandHandler("moj_profil", profile_command))
    app.add_handler(CommandHandler("ponisti_filtere", reset_filters_command))

    app.add_handler(CommandHandler("analitika", analytics_command))
    app.add_handler(CommandHandler("kvartovi", neighborhoods_command))
    app.add_handler(CommandHandler("best_buy", best_buy_command))
    app.add_handler(CommandHandler("najnovije", latest_command))
    app.add_handler(CommandHandler("kvart", neighborhood_listings_command))
    app.add_handler(CommandHandler("spremljeno", saved_command))

    app.add_handler(CallbackQueryHandler(button_callback_handler))

    logging.info("\U0001F916 Bot sluša vaše komande u Telegramu...")
    try:
        app.run_polling()
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    run_bot_listener()