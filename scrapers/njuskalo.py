import json
import logging
import re
import time
import urllib.parse
import requests
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from telegram.ext import Application
from database.database import save_or_update_listing, get_connectivity, get_listing_by_id

from bot.notifier import notify_users_about_listing

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BASE_URL = "https://www.njuskalo.hr"
OSIJEK_URL = "https://www.njuskalo.hr/iznajmljivanje-stanova/osijek"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "hr-HR,hr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Ch-Ua": '"Chromium";v="128", "Not=A?Brand";v="24", "Google Chrome";v="128"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1"
}


def parse_price(price_raw) -> float:
    if price_raw is None or price_raw == "":
        return 0.00
    if isinstance(price_raw, (int, float)):
        return float(price_raw)

    text = str(price_raw).replace("€", "").replace("EUR", "").strip()
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
            cursor.execute("select id, name from locations")
            locations = cursor.fetchall()
            for loc in locations:
                if loc["name"].lower() in text_lower:
                    return loc["id"]
    except Exception:
        return None

    return None


def extract_external_id(url: str) -> str:
    match = re.search(r"oglas-(\d+)", url)
    if match:
        return match.group(1)
    return url.rstrip("/").split("/")[-1]


def parse_njuskalo_card(card: BeautifulSoup) -> Optional[Dict]:
    title_el = card.select_one(".entity-title a, .EntityList-item--Regular .entity-title, a[href*='oglas-']")
    if not title_el or not title_el.get("href"):
        return None

    raw_url = title_el["href"]
    if raw_url.startswith("#") or "javascript" in raw_url:
        return None

    url = urllib.parse.urljoin(BASE_URL, raw_url)
    title = title_el.get_text(strip=True)

    price_el = card.select_one(".price--eur, .price-items, .entity-prices, .price")
    price_text = price_el.get_text(strip=True) if price_el else ""
    price = parse_price(price_text)

    if price == 0:
        return None

    description_el = card.select_one(".entity-description, .entity-subtitle, .entity-body")
    description = description_el.get_text(strip=True) if description_el else ""

    location_el = card.select_one(".entity-description-main, .entity-location")
    location_text = location_el.get_text(strip=True) if location_el else ""

    combined_text = f"{title} {description} {location_text}"
    area_sqm = parse_area(combined_text)
    ext_id = extract_external_id(url)
    location_id = match_location_id(combined_text)

    img_tag = card.find("img", class_="entity-thumbnail-img") or card.find("img")
    image_url = None
    if img_tag:
        image_url = img_tag.get("data-src") or img_tag.get("src")
        if image_url and image_url.startswith("//"):
            image_url = "https:" + image_url

    return {
        "external_id": ext_id,
        "source_platform": "Njuškalo",
        "title": title,
        "description": description,
        "price": price,
        "area_sqm": area_sqm,
        "location_id": location_id,
        "raw_address": "Osijek",
        "url": url,
        "image_url": image_url,
    }


def scrape_njuskalo_osijek(max_pages: int = 5) -> List[Dict]:
    all_listings = []
    seen_urls = set()
    consecutive_empty_pages = 0
    EARLY_STOP_AFTER = 2

    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        logging.info("Acquiring session cookies from Njuškalo homepage...")
        home_resp = session.get(BASE_URL, timeout=12)
        if home_resp.status_code != 200:
            logging.warning(f"Homepage returned status {home_resp.status_code}, proceeding anyway.")
    except Exception as e:
        logging.warning(f"Could not pre-fetch homepage cookies: {e}, proceeding anyway.")

    for page in range(1, max_pages + 1):
        logging.info(f"Scraping Njuškalo (page {page}/{max_pages})... \U0001f5e1")

        page_url = f"{OSIJEK_URL}?page={page}"
        page_headers = {
            **HEADERS,
            "Referer": BASE_URL if page == 1 else f"{OSIJEK_URL}?page={page-1}"
        }

        try:
            response = session.get(page_url, headers=page_headers, timeout=12)

            if response.status_code == 403:
                logging.error("\u274c Njuškalo blocked the request (403 Forbidden). Anti-bot protection active.")
                break

            if response.status_code != 200:
                logging.error(f"\u274c Njuškalo returned status {response.status_code} for URL: {page_url}")
                break

            soup = BeautifulSoup(response.text, "html.parser")
            cards = soup.select(".EntityList--ListItemRegular .EntityList-item, .EntityList--cards .EntityList-item, article.EntityList-item")

            if not cards:
                cards = soup.select("li.EntityList-item")

            if not cards:
                logging.info(f"No listing elements found on page {page}.")
                consecutive_empty_pages += 1
                if consecutive_empty_pages >= EARLY_STOP_AFTER:
                    logging.info(f"Stopping early after {EARLY_STOP_AFTER} consecutive empty pages.")
                    break
                continue

            page_count = 0
            for card in cards:
                parsed = parse_njuskalo_card(card)
                if parsed and parsed["url"] not in seen_urls:
                    seen_urls.add(parsed["url"])
                    all_listings.append(parsed)
                    page_count += 1

            if page_count == 0:
                consecutive_empty_pages += 1
                if consecutive_empty_pages >= EARLY_STOP_AFTER:
                    logging.info(f"No new valid listings on {EARLY_STOP_AFTER} consecutive pages, stopping.")
                    break
            else:
                consecutive_empty_pages = 0

            logging.info(f"Found {page_count} new listings on page {page}")

            if page < max_pages:
                time.sleep(2.0)

        except Exception as e:
            logging.error(f"\u274c Error fetching Njuškalo page {page}: {e}")
            break

    return all_listings


async def run_njuskalo_scraper_and_save(max_pages: int = 5, app: Optional[Application] = None) -> Dict[str, int]:
    fetched_listings = scrape_njuskalo_osijek(max_pages=max_pages)

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