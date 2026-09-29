import logging
from scrapers.index_hr import scrape_index_osijek
from scrapers.njuskalo import scrape_njuskalo_osijek
from database.database import save_or_update_listing
from notifier.telegram_notifier import send_telegram_notification

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def run_pipeline(max_pages: int = 10):
    logging.info("\U0001f5e1 Starting scraping operation and notification workflow...")

    index_listings = scrape_index_osijek(max_pages=max_pages)
    njuskalo_listings = scrape_njuskalo_osijek(max_pages=max_pages)

    listings = index_listings + njuskalo_listings

    stats = {"inserted": 0, "price_drop": 0, "notified": 0}

    for item in listings:
        status, listing_id = save_or_update_listing(item)
        
        if listing_id:
            item["id"] = listing_id

        if status in ("inserted", "INSERTED"):
            stats["inserted"] += 1
            if send_telegram_notification(item, event_type="new"):
                stats["notified"] += 1

        elif status in ("price_drop", "PRICE_DROP"):
            stats["price_drop"] += 1
            if send_telegram_notification(item, event_type="price_drop"):
                stats["notified"] += 1

    logging.info(
        f"\U0001f680 Finished! New: {stats['inserted']}, "
        f"price drops: {stats['price_drop']}, "
        f"sent notifications: {stats['notified']}"
    )


if __name__ == "__main__":
    run_pipeline(max_pages=10)