import logging
from scrapers.index_hr import scrape_index_osijek
from database.database import save_or_update_listing
from notifier.telegram_notifier import send_telegram_notification

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def run_pipeline(max_pages: int = 2):
    logging.info("\U0001F52A Starting scraping operation and notification of workflow...")

    listings = scrape_index_osijek(max_pages=max_pages)

    stats = {"inserted": 0, "price_updated": 0, "notified": 0}

    for item in listings:
        status, _ = save_or_update_listing(item)

        if status in ("inserted", "INSERTED"):
            stats["inserted"] += 1
            if send_telegram_notification(item, event_type="new"):
                stats["notified"] += 1
        elif status in ("price_updated", "PRICE_UPDATED"):
            stats["price_updated"] += 1
            if send_telegram_notification(item, event_type="price_drop"):
                stats["notified"] += 1

    logging.info(f"\U0001F680 Finished! New: {stats['inserted']}, updated prices: {stats['price_updated']}, send notifications: {stats['notified']}")

if __name__ == "__main__":
    run_pipeline(max_pages=2)