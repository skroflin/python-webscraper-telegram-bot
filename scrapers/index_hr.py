import json
import logging
import re
import time
import urllib.parse
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional, Tuple
from database.database import save_or_update_listing, get_connectivity

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BASE_URL = "https://www.index.hr"
SEARCH_URL = (
    "https://www.index.hr/oglasi/nekretnine/najam-stanova/osijek/pretraga?"
    "searchQuery=%7B%22category%22%3A%22najam-stanova%22%2C%22module%22%3A%22nekretnine%22%2C"
    "%22sortOption%22%3A4%2C%22includeCityIds%22%3A%5B%22bd972dcf-a9f4-471b-89e5-c0e4c4117f43%22%5D%7D"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "hr-HR,hr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.index.hr/oglasi/",
    "Sec-Ch-Ua": '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1"
}

def parse_price(price_raw) -> float:
    """Scrape numeric value for price in EUR."""
    if not price_raw:
        return 0.00
    if isinstance(price_raw, (int, float)):
        return float(price_raw)

    text = str(price_raw).replace("€", "").replace("EUR", "").strip()
    text = text.replace(".", "").replace(",", ".")
    match = re.search(r"(\d+(\.\d+)?)", text)
    return float(match.group(1)) if match else 0.0

def parse_area(text: str) -> Optional[float]:
    """Extracting quadrature (m2) from title or description"""
    if not text:
        return None
    match = re.search(r"(\d+([\.,]\d+)?)\s*(m2|m²|kvadrat|kvadrata|kvm)", text, re.IGNORECASE)
    if match:
        val = match.group(1).replace(",", ".")
        return float(val)
    return None

def match_location_id(title_and_text: str) -> Optional[int]:
    """Mapping neighborhood names from ad text and Ids in table `locations`."""
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
        pass

    neighborhood_map = {
        "centar": 1,
        "retfala": 2,
        "sjenjak": 3,
        "jug2": 4, "jug 2": 4,
        "donji grad": 5, "dgo": 5,
        "gornji grad": 6, "ggo": 6,
        "tvrđa": 7, "tvrda": 7,
        "industrijska": 8,
        "novi grad": 9, "ngo": 9
    }

    for name, loc_id in neighborhood_map.items():
        if name in text_lower:
            return loc_id

    return None

def extract_from_next_data(soup: BeautifulSoup) -> Tuple[List[Dict], Optional[str]]:
    """Trying to fetch ad from Next.js JSON container (___NEXT_DATA__)."""
    script_tag = soup.find("script", id="__NEXT_DATA__")
    if not script_tag:
        return [], "Tag <script id='__NEXT_DATA__'> doesn't exist in the HTML"
    if not script_tag.string:
        return [], "Tag __NEXT_DATA__ is empty"

    try:
        data = json.loads(script_tag.string)
        page_props = data.get("props", {}).get("pageProps", {})

        items = (
            page_props.get("searchResults", {}).get("ads")
            or page_props.get("ads")
            or page_props.get("initialData", {}).get("ads")
            or []
        )

        if not items:
            return [], "JSON structure does not contain ad field or list is empty!"

        listings = []
        for item in items:
            url = item.get("url") or item.get("link") or item.get("canonicalUrl")
            if not url:
                continue

            if not url.startswith("http"):
                url = urllib.parse.urljoin(BASE_URL, url)

            title = item.get("title") or item.get("heading") or "No title"
            price_raw = item.get("price") if item.get("price") is not None else item.get("priceEur")
            price = parse_price(price_raw)

            if price == 0:
                continue

            description = item.get("description") or ""
            area_sqm = item.get("surfaceArea") or item.get("area") or parse_area(title) or parse_area(description)

            if area_sqm:
                try:
                    area_sqm = float(str(area_sqm).replace(",", "."))
                except ValueError:
                    area_sqm = None

            location_id = match_location_id(f"{title} {description}")

            listings.append({
                "external_id": str(item.get("id") or item.get("adId") or ""),
                "source_platform": "Index Oglasnik",
                "title": title.strip(),
                "description": description.strip(),
                "price": float(price),
                "area_sqm": area_sqm,
                "location_id": location_id,
                "raw_address": "Osijek",
                "url": url,
            })

        if not listings:
            return [], "Not one ad was successfully extracted after filtration"

        return listings, None

    except Exception as e:
        error_msg = f"\u274C Unsuccessful parsing __NEXT_DATA__ JSON: {e}"
        logging.warning(error_msg)
        return [], error_msg

def extract_from_html(soup: BeautifulSoup) -> List[Dict]:
    listings = []
    seen_urls = set()

    for a_tag in soup.find_all("a", href=True):
        try:
            raw_href = a_tag["href"]
            
            id_match = re.search(r"/(\d+)(?:\?.*)?$", raw_href)
            if not id_match:
                continue

            external_id = id_match.group(1)
            url = urllib.parse.urljoin(BASE_URL, raw_href)

            if url in seen_urls:
                continue

            title = a_tag.get("title", "").strip()
            if not title:
                title_el = a_tag.select_one("[class*='title'], [class*='Title'], h2, h3, h4")
                if title_el:
                    title = title_el.get_text(strip=True)
                else:
                    lines = [line.strip() for line in a_tag.get_text("\n").split("\n") if line.strip()]
                    title = lines[0] if lines else ""

            if not title or len(title) < 3 or "prikaz" in title.lower():
                continue

            seen_urls.add(url)

            price_el = a_tag.select_one("[class*='price'], [class*='Price']")
            if price_el:
                price_text = price_el.get_text(strip=True)
            else:
                card_text = a_tag.get_text(" ")
                price_match = re.search(r"(\d+[\d\.,]*\s*€|\d+[\d\.,]*\s*EUR)", card_text)
                price_text = price_match.group(1) if price_match else ""

            price = parse_price(price_text)

            area_sqm = parse_area(title)
            location_id = match_location_id(title)

            listings.append({
                "external_id": external_id,
                "source_platform": "Index Oglasnik",
                "title": title,
                "description": "",
                "price": price,
                "area_sqm": area_sqm,
                "location_id": location_id,
                "raw_address": "Osijek",
                "url": url,
            })

        except Exception as e:
            logging.debug(f"\u274C Error parsing HTML card: {e}")

    return listings

def scrape_index_osijek(max_pages: int = 2) -> List[Dict]:
    """Main scraping function: parsing through specific page number"""
    all_listings = []
    seen_urls = set()

    for page in range(1, max_pages + 1):
        url = SEARCH_URL
        if page > 1:
            url += f"&page={page}"

        logging.info(f"Scraping Index Oglasnik (page {page}/{max_pages})... \U0001F52A")

        try:
            response = requests.get(url, headers=HEADERS, timeout=12)
            with open("debug_index.html", "w", encoding="utf-8") as f:
                f.write(response.text)
            response.raise_for_status()
        except requests.RequestException as e:
            logging.error(f"\u274C Error whilst fetching page {page}: {e}")
            break

        soup = BeautifulSoup(response.content, "html.parser")

        page_title = soup.title.string.strip() if soup.title else "No Title"
        logging.info(f"Page title: '{page_title}' | Response length: {len(response.text)} bytes")

        listings, error_reason = extract_from_next_data(soup)

        if not listings:
            logging.error(f"\U00002139 __NEXT_DATA__ not found/supported: ({error_reason}), using HTML parsers!")
            listings = extract_from_html(soup)

        page_count = 0
        for item in listings:
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                all_listings.append(item)
                page_count += 1

        logging.info(f"Found {page_count} new ads on page {page}")

        if page < max_pages:
            time.sleep(1.5)

    return all_listings

def run_index_scraper_and_save(max_pages: int = 2) -> Dict[str, int]:
    """Starting scraper and saving/inserting newly found ads to db."""
    fetched_listings = scrape_index_osijek(max_pages=max_pages)

    stats = {
        "inserted": 0,
        "exists": 0,
        "price_updated": 0,
        "duplicates": 0
    }

    for item in fetched_listings:
        status, _ = save_or_update_listing(item)
        if status in ("inserted", "INSERTED"):
            stats["inserted"] += 1
        elif status in ("exists", "EXISTS"):
            stats["exists"] += 1
        elif status in ("price_updated", "PRICE_UPDATED"):
            stats["price_updated"] += 1
        elif status in ("duplicate_cross_post", "DUPLICATE_CROSS_POST"):
            stats["duplicates"] += 1

    return stats