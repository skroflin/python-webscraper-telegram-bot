import json
import logging
import re
import time
import urllib.parse
import requests
from typing import List, Dict, Optional, Tuple
from bs4 import BeautifulSoup

from bot.notifier import notify_users_about_listing
from telegram.ext import Application
from database.database import save_or_update_listing, get_connectivity, get_listing_by_id

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

API_URL = "https://www.index.hr/oglasi/api/aditem"
BASE_URL = "https://www.index.hr/oglasi"
OSIJEK_CITY_ID = "bd972dcf-a9f4-471b-89e5-c0e4c4117f43"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "hr-HR,hr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.index.hr/oglasi/najam-stanova/grad-osijek",
}

APARTMENT_URL_MARKER = "/oglasi/nekretnine/najam-stanova/"
APARTMENT_CATEGORY_TERMS = (
    "najam-stanova",
    "najam stanova",
    "stanovi za najam",
    "stan za najam",
    "stan",
    "garsonijera",
)
APARTMENT_TITLE_PATTERNS = (
    r"\bstan\w*",
    r"\bgarsonijer\w*",
    r"\bjednosob\w*",
    r"\bdvosob\w*",
    r"\btrosob\w*",
    r"\bčetverosob\w*",
    r"\bcetverosob\w*",
    r"\bpetosob\w*",
    r"\bšesterosob\w*",
    r"\b[1-6]\s*s(?:\s*\+\s*db)?\b",
)
RENTAL_TITLE_PATTERNS = (
    r"\bnajam\w*",
    r"\biznajm\w*",
    r"\bizdaje\w*",
    r"\bmjeseč\w*",
    r"\bmjesec\w*",
    r"\bdugoroč\w*",
    r"\bdugoroc\w*",
    r"\brent\b",
)
VEHICLE_TERMS = (
    "auto",
    "automobil",
    "vozilo",
    "motor",
    "motocikl",
    "motocik",
    "skuter",
    "moped",
    "kombi",
    "kamion",
    "prikolica",
    "quad",
    "atv",
    "traktor",
    "plovilo",
    "brod",
    "čamac",
    "camac",
    "jahta",
    "guma",
    "gume",
    "felga",
    "felge",
    "registracij",
)


def _flatten_for_filter(value) -> str:
    """Turn nested API metadata into a searchable text string."""
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(_flatten_for_filter(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten_for_filter(v) for v in value)
    return str(value)


def is_strict_apartment_rental(item: Optional[Dict], url: Optional[str] = None) -> bool:
    """
    Fail-closed filter:
      1) reject an explicitly non-apartment/category URL;
      2) if Index metadata contains category information, it must point to
         residential apartment rentals;
      3) reject obvious vehicle/non-real-estate listings;
      4) require a strong apartment signal in title/description.
    """
    item = item or {}
    raw_url = (
        url
        or item.get("url")
        or item.get("link")
        or item.get("canonicalUrl")
        or item.get("canonical_url")
        or ""
    )
    url_lower = str(raw_url).lower()

    if raw_url and APARTMENT_URL_MARKER not in url_lower:
        return False

    category_keys = (
        "category",
        "categoryName",
        "categoryTitle",
        "categoryPath",
        "categorySlug",
        "subcategory",
        "subcategoryName",
    )
    category_text = " ".join(
        _flatten_for_filter(item.get(key)).lower()
        for key in category_keys
        if item.get(key) is not None
    )

    if category_text:
        if any(term in category_text for term in VEHICLE_TERMS):
            return False

        if any(
            term in category_text
            for term in (
                "automobili",
                "motocikli",
                "vozila",
                "plovila",
                "dijelovi",
                "prijevoz",
            )
        ):
            return False

    type_text = " ".join(
        _flatten_for_filter(item.get(key)).lower()
        for key in ("type", "typeName", "adType", "section")
        if item.get(key) is not None
    )
    if any(term in type_text for term in VEHICLE_TERMS):
        return False

    title = _flatten_for_filter(item.get("title")).lower()
    description = _flatten_for_filter(
        item.get("description") or item.get("summary") or item.get("text") or ""
    ).lower()
    text = f"{title} {description}".strip()

    if any(term in text for term in VEHICLE_TERMS):
        return False

    has_apartment_signal = any(
        re.search(pattern, text, re.IGNORECASE)
        for pattern in APARTMENT_TITLE_PATTERNS
    )
    has_rental_signal = any(
        re.search(pattern, text, re.IGNORECASE)
        for pattern in RENTAL_TITLE_PATTERNS
    )

    return has_apartment_signal and has_rental_signal


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
    match = re.search(r"(\d+([\.,]\d+)?)\s*(m2|m²|kvadrat|kvadrata|kvm)", str(text), re.IGNORECASE)
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


def parse_api_item(item: Dict) -> Optional[Dict]:
    if not is_strict_apartment_rental(item):
        logging.info(
            "Skipping non-apartment/non-rental item from Index API: %s",
            item.get("title") or item.get("id") or item.get("code"),
        )
        return None

    smart_link = item.get("smartLink")
    code = item.get("code") or item.get("id")

    if smart_link and code:
        url = f"{BASE_URL}/nekretnine/najam-stanova/oglas/{smart_link}/{code}"
    elif code:
        url = f"{BASE_URL}/nekretnine/najam-stanova/oglas/{code}"
    else:
        return None

    # Final URL-level guard before anything is returned to the DB layer.
    if not is_strict_apartment_rental(item, url=url):
        return None

    title = (item.get("title") or "Bez naslova").strip()
    price = parse_price(item.get("price"))

    if price == 0:
        return None

    summary = item.get("summary") or {}
    area_sqm = summary.get("area")
    if area_sqm is not None:
        try:
            area_sqm = float(area_sqm)
        except (ValueError, TypeError):
            area_sqm = parse_area(title)
    else:
        area_sqm = parse_area(title)

    settlement = item.get("settlementName") or ""
    description = f"Naselje/Kvart: {settlement}".strip() if settlement else ""
    location_id = match_location_id(f"{title} {settlement}")

    image_url = item.get("iconUrl") or item.get("imageUrl") or item.get("image") or item.get("defaultImage")

    return {
        "external_id": str(code),
        "source_platform": "Index Oglasnik",
        "title": title,
        "description": description,
        "price": price,
        "area_sqm": area_sqm,
        "location_id": location_id,
        "raw_address": f"Osijek, {settlement}".strip(", "),
        "url": url,
        "image_url": image_url,
    }


def scrape_index_osijek(max_pages: int = 10) -> List[Dict]:
    """Scrape Index.hr Oglasnik for Osijek apartment rentals.

    The API does not honour city filters server-side — it returns all Croatian
    listings. We post-filter every response item by cityId == OSIJEK_CITY_ID.
    With ~1 Osijek listing per 24 returned we scrape up to `max_pages` pages,
    but stop early if we find no Osijek listings for 3 consecutive pages.
    """
    all_listings = []
    seen_urls = set()
    consecutive_empty_pages = 0
    EARLY_STOP_AFTER = 3

    session = requests.Session()
    session.headers.update({
        "User-Agent": HEADERS["User-Agent"],
        "Accept-Language": HEADERS["Accept-Language"],
    })

    try:
        logging.info("Acquiring session cookies from Index.hr...")
        page_resp = session.get(
            "https://www.index.hr/oglasi/nekretnine/najam-stanova/osijek/pretraga",
            headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
            timeout=15,
        )
        if page_resp.status_code != 200:
            logging.warning(f"Cookie page returned {page_resp.status_code}, proceeding anyway.")
    except Exception as e:
        logging.warning(f"Could not pre-fetch cookie page: {e}, proceeding anyway.")

    api_headers = {**HEADERS, "X-Requested-With": "XMLHttpRequest"}

    for page in range(1, max_pages + 1):
        logging.info(f"Scraping Index Oglasnik API (page {page}/{max_pages})... \U0001f5e1")

        search_query = {
            "category": "najam-stanova",
            "module": "nekretnine",
            "sortOption": 4,
            "includeCityIds": [OSIJEK_CITY_ID],
        }

        params = {
            "searchQuery": json.dumps(search_query, separators=(',', ':')),
            "page": page,
            "itemPerPage": 24,
        }

        try:
            response = session.get(API_URL, headers=api_headers, params=params, timeout=10)

            if response.status_code != 200:
                logging.error(f"\u274c Index API returned status {response.status_code}: {response.text}")
                break

            data = response.json()
            raw_items = data.get("data", []) or []

            if not raw_items:
                logging.info(f"No listings found on page {page}, stopping.")
                break

            osijek_items = [i for i in raw_items if i.get("cityId") == OSIJEK_CITY_ID]

            apartment_items = [i for i in osijek_items if is_strict_apartment_rental(i)]

            logging.info(
                f"Page {page}: {len(raw_items)} total returned, "
                f"{len(osijek_items)} from Osijek, "
                f"{len(apartment_items)} confirmed apartment rentals"
            )

            page_count = 0
            for item in apartment_items:
                parsed = parse_api_item(item)
                if parsed and parsed["url"] not in seen_urls:
                    seen_urls.add(parsed["url"])
                    all_listings.append(parsed)
                    page_count += 1

            if page_count == 0:
                consecutive_empty_pages += 1
                if consecutive_empty_pages >= EARLY_STOP_AFTER:
                    logging.info(f"No Osijek listings for {EARLY_STOP_AFTER} consecutive pages, stopping early.")
                    break
            else:
                consecutive_empty_pages = 0

            logging.info(f"Added {page_count} new Osijek listings from page {page}")

            if page < max_pages:
                time.sleep(1.0)

        except Exception as e:
            logging.error(f"\u274c Error fetching API on page {page}: {e}")
            break

    return all_listings



async def run_index_scraper_and_save(max_pages: int = 2, app: Optional[Application] = None) -> Dict[str, int]:
    fetched_listings = scrape_index_osijek(max_pages=max_pages)

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


def extract_from_next_data(soup: BeautifulSoup) -> Tuple[List[Dict], Optional[str]]:
    script_tag = soup.find("script", id="__NEXT_DATA__")
    if not script_tag or not script_tag.string:
        return [], "Tag <script id='__NEXT_DATA__'> does not exist in HTML"

    try:
        data = json.loads(script_tag.string)
        page_props = data.get("props", {}).get("pageProps", {})
        items = (
            page_props.get("searchResults", {}).get("ads")
            or page_props.get("ads")
            or page_props.get("initialData", {}).get("ads")
            or []
        )

        listings = []
        for item in items:
            url = item.get("url") or item.get("link")
            if not url:
                continue

            if not is_strict_apartment_rental(item, url=url):
                continue
            if not url.startswith("http"):
                url = urllib.parse.urljoin(BASE_URL, url)

            title = item.get("title") or "Bez naslova"
            price = parse_price(item.get("price") or item.get("priceEur"))
            if price == 0:
                continue

            desc = item.get("description") or ""
            area_sqm = item.get("surfaceArea") or parse_area(title)

            listings.append({
                "external_id": str(item.get("id") or ""),
                "source_platform": "Index Oglasnik",
                "title": title.strip(),
                "description": desc.strip(),
                "price": float(price),
                "area_sqm": float(area_sqm) if area_sqm else None,
                "location_id": match_location_id(f"{title} {desc}"),
                "raw_address": "Osijek",
                "url": url,
            })
        return listings, None
    except Exception as e:
        return [], str(e)


def extract_from_html(soup: BeautifulSoup) -> List[Dict]:
    listings = []

    cards = soup.select(".results-page .element, a.m-card, .ad-box, article, div[class*='card'], div[class*='ad-']")

    if not cards:
        cards = [
            a for a in soup.find_all("a", href=True)
            if "/oglasi/" in a["href"] and any(char.isdigit() for char in a["href"])
        ]

    seen_urls_in_page = set()

    for card in cards:
        url = card.get("href") if card.name == "a" else None
        if not url:
            a_tag = card.find("a", href=True)
            url = a_tag["href"] if a_tag else None

        if not url:
            continue

        if not url.startswith("http"):
            url = urllib.parse.urljoin(BASE_URL, url)

        if url.endswith("/grad-osijek") or "najam-stanova?" in url or url in seen_urls_in_page:
            continue

        seen_urls_in_page.add(url)

        title_el = card.select_one(".title, .m-card__title, h3, h2, strong")
        title = title_el.get_text(strip=True) if title_el else card.get_text(strip=True)

        if not is_strict_apartment_rental({"title": title}, url=url):
            continue

        if len(title) > 200:
            title = title[:197] + "..."

        price_el = card.select_one(".price, .m-card__price, .price-eur, span[class*='price']")
        price_text = price_el.get_text(strip=True) if price_el else card.get_text(strip=True)
        price = parse_price(price_text)

        if price == 0:
            continue

        ext_id = url.rstrip("/").split("/")[-1].replace(".aspx", "")

        img_tag = card.find("img")
        image_url = None
        if img_tag:
            image_url = img_tag.get("src") or img_tag.get("data-src")

        listings.append({
            "external_id": ext_id,
            "source_platform": "Index Oglasnik",
            "title": title,
            "description": "",
            "price": float(price),
            "area_sqm": parse_area(title),
            "location_id": match_location_id(title),
            "raw_address": "Osijek",
            "url": url,
            "image_url": image_url,
        })

    return listings