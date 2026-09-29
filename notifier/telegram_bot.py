import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from config import TELEGRAM_BOT_TOKEN
from database.database import get_connectivity

logging.basicConfig(level=logging.INFO)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "\U0001F44B **Bok! Ja sam tvoj Osijek Stanovi Bot.**\n\n"
        "Dostupne naredbe:\n"
        f"\n─────────────────\n"
        "\U0001F4CA /analitika - Prosječne cijene i statistika\n"
        "\U0001F3AB /best_buy - Najpovoljniji stanovi po m²\n"
        "\U0001F526 /najnovije - Zadnjih 5 stanova iz baze"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def analytics_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        with get_connectivity() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    AVG(price) as avg_price,
                    AVG(price / NULLIF(area_sqm, 0)) as avg_sqm_price
                FROM listings
            """)
            stats = cursor.fetchone()

        msg = (
            "\U0001F4CA **Analitika tržišta najma u Osijeku**\n\n"
            f"\n─────────────────\n"
            f"- Ukupno stanova u bazi: **{stats['total']}**\n"
            f"- Prosječna mjesečna najamnina: **{stats['avg_price']:.2f} €**\n"
            f"- Prosječna cijena po m²: **{stats['avg_sqm_price']:.2f} €/m²**"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"\U0001F506 Greška pri dohvaćanju analitike: {e}")

async def best_buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        with get_connectivity() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT title, price, area_sqm, (price / area_sqm) as price_per_sqm, url
                FROM listings
                WHERE area_sqm IS NOT NULL AND area_sqm > 0 AND price > 0
                ORDER BY price_per_sqm ASC
                LIMIT 3
            """)
            listings = cursor.fetchall()

        if not listings:
            await update.message.reply_text("\U00002139 Nema dovoljno podataka o kvadraturama za izračun.")
            return

        await update.message.reply_text("\U0001F31F **Top 3 najpovoljnija stana po m²:**", parse_mode="Markdown")

        for item in listings:
            text = (
                f"\U0001F31F **{item['title']}**\n"
                f"\n─────────────────\n"
                f"\U0001F4B0 Cijena: **{item['price']:.2f} €** ({item['price_per_sqm']:.2f} €/m²)\n"
                f"\U0001F4D0 Površina: **{item['area_sqm']} m²**\n"
            )
            keyboard = [[InlineKeyboardButton("Pogledaj priliku \U0001F517", url=item["url"])]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)

    except Exception as e:
        logging.error(f"\U0001F506 Error in /best_buy: {e}")
        await update.message.reply_text("\U0001F506 Greška pri dohvaćanju najpovoljnijih stanova.")

async def latest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        with get_connectivity() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT title, price, area_sqm, source_platform, url
                FROM listings
                ORDER BY created_at DESC
                LIMIT 5
            """)
            listings = cursor.fetchall()

        if not listings:
            await update.message.reply_text("\U00002139 Trenutno nema unesenih stanova u bazi.")
            return

        await update.message.reply_text("\U0001F4CB **Zadnjih 5 stanova u bazi:**", parse_mode="Markdown")

        for item in listings:
            area = f"{item['area_sqm']} m²" if item["area_sqm"] else "Nije navedeno"
            text = (
                f"\U0001F31F **{item['title']}**\n"
                f"\n─────────────────\n"
                f"\U0001F4B0 Cijena: **{item['price']:.2f} €**\n"
                f"\U0001F4D0 Površina: **{area}**\n"
                f"\U0001F4CB Izvor: **{item['source_platform']}**\n"
            )
            keyboard = [[InlineKeyboardButton("Pogledaj oglas \U0001F517", url=item["url"])]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)

    except Exception as e:
        logging.error(f"\U0001F506 Error in /najnovije: {e}")
        await update.message.reply_text("\U0001F506 Greška pri dohvaćanju stanova iz baze.")

def run_bot_listener():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("analitika", analytics_command))
    app.add_handler(CommandHandler("best_buy", best_buy_command))
    app.add_handler(CommandHandler("najnovije", latest_command))

    logging.info("\U0001F44B Bot sluša vaše komande u Telegramu...")
    app.run_polling()

if __name__ == "__main__":
    run_bot_listener()