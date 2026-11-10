import asyncio
import logging
import os
import signal
import sys
from datetime import datetime
from typing import Optional

from config import SCRAPE_INTERVAL_MINUTES, TELEGRAM_BOT_TOKEN
from database.database import init_db
from main import run_pipeline
from scrapers.health_check import run_health_check
from bot.notifier import send_admin_alert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Worker] %(message)s",
)


class ScraperWorker:
    """
    Dedicated background worker responsible for periodic scraping cycles
    and listing health check maintenance without blocking the interactive Telegram bot.
    """

    def __init__(self, interval_minutes: int = SCRAPE_INTERVAL_MINUTES):
        self.interval_seconds = max(60, interval_minutes * 60)
        self.running = True
        self.last_health_check_day: Optional[int] = None

    def stop(self, *args):
        logging.info("\U0001F6D1 Received termination signal. Gracefully stopping scraper worker...")
        self.running = False

    async def run(self):
        logging.info("\U0001F680 Scraper worker daemon starting up...")
        logging.info("\U000023F0 Configured scrape interval: %d minutes.", self.interval_seconds // 60)

        init_db()

        await asyncio.sleep(2)

        while self.running:
            start_time = datetime.now()
            logging.info("\U0001F504 === Starting scheduled scrape cycle ===")

            try:
                stats = await run_pipeline(max_pages=3)
                logging.info("\U00002705 Cycle completed successfully: %s", stats)
            except Exception as e:
                logging.exception("\U0000274c Error during scraping pipeline execution: %s", e)
                await send_admin_alert(
                    f"\U000026a0 *[Worker Greška]*\n\nDošlo je do greške u scraper ciklusu:\n`{e}`",
                    alert_key="worker_cycle_error",
                    cooldown_seconds=3600,
                )

            now = datetime.now()
            if now.hour == 3 and self.last_health_check_day != now.day:
                logging.info("\U0001F9F9 === Starting daily listing health check ===")
                try:
                    checked, deactivated = await asyncio.to_thread(run_health_check)
                    logging.info("\U0001F9F9 Health check complete: %d checked, %d marked inactive.", checked, deactivated)
                    self.last_health_check_day = now.day
                except Exception as e:
                    logging.exception("\U0000274c Error during daily health check: %s", e)

            elapsed = (datetime.now() - start_time).total_seconds()
            sleep_needed = max(5.0, self.interval_seconds - elapsed)
            logging.info("\U0001F6CC Scraper sleeping for %d seconds until next cycle...", int(sleep_needed))

            sleep_steps = int(sleep_needed)
            for _ in range(sleep_steps):
                if not self.running:
                    break
                await asyncio.sleep(1)

        logging.info("\U0001F44B Scraper worker has shut down cleanly.")


def main():
    worker = ScraperWorker(interval_minutes=SCRAPE_INTERVAL_MINUTES)

    if sys.platform != "win32":
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, worker.stop)
    else:
        signal.signal(signal.SIGINT, worker.stop)
        signal.signal(signal.SIGTERM, worker.stop)

    try:
        asyncio.run(worker.run())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Scraper worker terminated by user.")


if __name__ == "__main__":
    main()