import asyncio
import logging
from typing import Optional
from telegram.ext import Application, ApplicationBuilder

from config import TELEGRAM_BOT_TOKEN
from database.database import save_or_update_listing, get_listing_by_id, init_db
from scrapers.index_hr import scrape_index_osijek
from scrapers.njuskalo import scrape_njuskalo_osijek
from bot.notifier import notify_users_about_listing

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


async def run_pipeline(app: Optional[Application] = None, max_pages: int = 10) -> dict:
    logging.info("\U0001F5E1 Starting scraping operation and notification workflow...")

    init_db()

    index_listings = scrape_index_osijek(max_pages=max_pages)
    njuskalo_listings = scrape_njuskalo_osijek(max_pages=max_pages)

    listings = index_listings + njuskalo_listings

    stats = {"inserted": 0, "price_drop": 0, "duplicates": 0, "exists": 0}

    for item in listings:
        status, listing_id = save_or_update_listing(item)

        if status in ("inserted", "INSERTED"):
            stats["inserted"] += 1
            if app and listing_id:
                full_item = get_listing_by_id(listing_id)
                if full_item:
                    await notify_users_about_listing(app, full_item, event_type="inserted")

        elif status in ("price_drop", "PRICE_DROP"):
            stats["price_drop"] += 1
            if app and listing_id:
                full_item = get_listing_by_id(listing_id)
                if full_item:
                    full_item["old_price"] = item.get("old_price")
                    await notify_users_about_listing(app, full_item, event_type="price_drop")

        elif status in ("duplicate_cross_post", "DUPLICATE_CROSS_POST"):
            stats["duplicates"] += 1
            logging.info(f"\u2139\ufe0f Skipping duplicate notification (ID {listing_id}): {item.get('title')}")

        elif status in ("exists", "EXISTS"):
            stats["exists"] += 1

    logging.info(
        f"\U0001F680 Scraping finished! New: {stats['inserted']}, "
        f"Price drops: {stats['price_drop']}, "
        f"Duplicates: {stats['duplicates']}, "
        f"Existing: {stats['exists']}"
    )
    return stats


async def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    await app.initialize()
    await run_pipeline(app=app, max_pages=10)
    await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())