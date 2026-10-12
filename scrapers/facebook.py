import json
import logging
import re
import time
import urllib.parse
from typing import List, Dict, Optional
from bs4 import BeautifulSoup

from telegram.ext import Application
from database.database import save_or_update_listing, get_connectivity, get_listing_by_id
from bot.notifier import notify_users_about_listing

try:
    from scrapers.health_check import is_listing_text_inactive
except ImportError:
    def is_listing_text_inactive(text: str) -> bool:
        if not text:
            return False
        inactive_keywords = ["iznajmljeno", "prodano", "neaktivno", "rezervirano", "izdano"]
        return any(kw in text.lower() for kw in inactive_keywords)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BASE_URL = "https://www.facebook.com"
MARKETPLACE_OSIJEK_RENTALS_URL = "https://www.facebook.com/marketplace/osijek/propertyrentals"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)


def parse_price(price_raw) -> float:
    if price_raw is None or price_raw == "":
        return 0.00
    if isinstance(price_raw, (int, float)):
        return float(price_raw)

    text = str(price_raw).replace("€", "").replace("EUR", "").replace("kn", "").strip()
    text = text.replace(".", "").replace(",", ".")
    match = re.search(r"(\d+(\.\d+)?)", text)
    return float(match.group(1)) if match else 0.00


def parse_area(text: Optional[str]) -> Optional[float]:
    if not text:
        return None
    match = re.search(r"(\d+([\.,]\d+)?)\s*(m2|m²|kvadrat|kvadrata|kvm|m^2)", str(text), re.IGNORECASE)
    if match:
        val = match.group(1).replace(",", ".")
        return float(val)
    return None


def match_location_id(title_and_text: Optional[str]) -> Optional[int]:
    if not title_and_text:
        return None
    text_lower = title_and_text.lower()

    try:
        with get_connectivity() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name FROM locations")
            locations = cursor.fetchall()
            for loc in locations:
                if loc["name"].lower() in text_lower:
                    return loc["id"]
    except Exception as e:
        logging.debug(f"Error matching location_id: {e}")
        return None

    return None


def extract_external_id(url: str) -> str:
    match = re.search(r"/item/(\d+)", url)
    if match:
        return match.group(1)
    cleaned = url.split("?")[0].rstrip("/")
    return cleaned.split("/")[-1]


async def scrape_facebook_osijek(max_scrolls: int = 5) -> List[Dict]:
    """
    Scrapes Facebook Marketplace Osijek property rentals using Playwright.
    Handles dynamic JS loading and obfuscated DOM structures safely.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logging.error(
            "\u274c Playwright is not installed. Run `pip install playwright` "
            "and `playwright install chromium`."
        )
        return []

    listings = []
    seen_urls = set()

    logging.info("Starting Facebook Marketplace Playwright scraper... \U0001f5e1")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--lang=hr-HR,hr",
            ]
        )
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 800},
            locale="hr-HR"
        )
        page = await context.new_page()

        try:
            logging.info(f"Navigating to Facebook Marketplace Osijek: {MARKETPLACE_OSIJEK_RENTALS_URL}")
            await page.goto(MARKETPLACE_OSIJEK_RENTALS_URL, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            try:
                close_buttons = page.locator("div[role='dialog'] div[aria-label='Decline optional cookies'], div[role='dialog'] div[aria-label='Odbij neobvezne kolačiće'], div[aria-label='Close'], div[aria-label='Zatvori']")
                if await close_buttons.count() > 0:
                    await close_buttons.first.click()
                    await page.wait_for_timeout(1000)
            except Exception as e:
                logging.debug(f"No cookie/login overlay closed: {e}")

            for scroll in range(1, max_scrolls + 1):
                logging.info(f"Scrolling Facebook Marketplace ({scroll}/{max_scrolls})...")
                await page.evaluate("window.scrollBy(0, 1000)")
                await page.wait_for_timeout(2500)

            content = await page.content()
            soup = BeautifulSoup(content, "html.parser")

            item_links = soup.find_all("a", href=lambda h: h and "/marketplace/item/" in h)

            for link in item_links:
                href = link.get("href", "")
                if not href:
                    continue

                full_url = urllib.parse.urljoin(BASE_URL, href).split("?")[0]
                if full_url in seen_urls:
                    continue

                seen_urls.add(full_url)
                ext_id = extract_external_id(full_url)

                card_text = link.get_text(separator=" ", strip=True)
                if not card_text or is_listing_text_inactive(card_text):
                    continue

                price_match = re.search(r"(\d+[\d\.,]*\s*€|\d+[\d\.,]*\s*EUR|€\s*\d+[\d\.,]*)", card_text)
                price = parse_price(price_match.group(1)) if price_match else parse_price(card_text)

                if price == 0.0:
                    continue

                title = card_text
                if price_match:
                    title = title.replace(price_match.group(0), "").strip()

                if len(title) > 180:
                    title = title[:177] + "..."

                img_tag = link.find("img")
                image_url = img_tag.get("src") if img_tag else None

                area_sqm = parse_area(card_text)
                loc_id = match_location_id(card_text)

                listings.append({
                    "external_id": str(ext_id),
                    "source_platform": "Facebook Marketplace",
                    "title": title or "Stan u Osijeku (Facebook)",
                    "description": f"Facebook Marketplace oglas: {title}",
                    "price": float(price),
                    "area_sqm": area_sqm,
                    "location_id": loc_id,
                    "raw_address": "Osijek",
                    "url": full_url,
                    "image_url": image_url,
                })

        except Exception as e:
            logging.error(f"\u274c Error during Playwright Facebook scraping execution: {e}")
        finally:
            await browser.close()

    logging.info(f"Facebook Marketplace scraper finished. Total items extracted: {len(listings)}")
    return listings


async def run_facebook_scraper_and_save(max_scrolls: int = 5, app: Optional[Application] = None) -> Dict[str, int]:
    """
    Executes Facebook Marketplace scraping and saves/updates items in SQLite database,
    triggering Telegram notifications for new listings or price drops.
    """
    fetched_listings = await scrape_facebook_osijek(max_scrolls=max_scrolls)

    stats = {
        "inserted": 0,
        "exists": 0,
        "price_updated": 0,
        "duplicates": 0
    }

    for item in fetched_listings:
        status, listing_id = save_or_update_listing(item)

        if status in ("inserted", "INSERTED"):
            stats["inserted"] += 1
            if app and listing_id:
                full_item = get_listing_by_id(listing_id)
                if full_item:
                    await notify_users_about_listing(app, full_item, event_type="inserted")

        elif status in ("exists", "EXISTS"):
            stats["exists"] += 1

        elif status in ("price_updated", "PRICE_UPDATED", "price_drop", "price_increased"):
            stats["price_updated"] += 1
            if app and listing_id and status == "price_drop":
                full_item = get_listing_by_id(listing_id)
                if full_item:
                    full_item["old_price"] = item.get("old_price")
                    await notify_users_about_listing(app, full_item, event_type="price_drop")

        elif status in ("duplicate_cross_post", "DUPLICATE_CROSS_POST"):
            stats["duplicates"] += 1

    return stats