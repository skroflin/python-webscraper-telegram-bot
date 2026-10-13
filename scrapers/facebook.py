import asyncio
import logging
import os
import re
import urllib.parse
from typing import Dict, List, Optional, Set, Tuple

from bs4 import BeautifulSoup
from telegram.ext import Application

from database.database import (
    get_connectivity,
    get_listing_by_id,
    save_or_update_listing,
)
from bot.notifier import notify_users_about_listing

try:
    from scrapers.health_check import is_listing_text_inactive
except ImportError:
    def is_listing_text_inactive(text: str) -> bool:
        if not text:
            return False

        keywords = (
            "iznajmljeno",
            "prodano",
            "neaktivno",
            "rezervirano",
            "izdano",
        )
        lowered = text.casefold()
        return any(keyword in lowered for keyword in keywords)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

BASE_URL = "https://www.facebook.com"

MARKETPLACE_OSIJEK_RENTALS_URL = (
    "https://www.facebook.com/marketplace/osijek/propertyrentals"
)

FACEBOOK_GROUP_URLS = [
    "https://www.facebook.com/groups/stanoviosijeknajam/",
    "https://www.facebook.com/groups/930964456965628/",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)

FACEBOOK_STORAGE_STATE = os.getenv("FACEBOOK_STORAGE_STATE")

DEFAULT_MAX_SCROLLS = 5
MAX_TITLE_LENGTH = 180
MAX_DESCRIPTION_LENGTH = 5000
NAVIGATION_TIMEOUT_MS = 30000
INITIAL_WAIT_MS = 2500
SCROLL_WAIT_MS = 1800


def parse_price(price_raw) -> float:
    """
    Converts a price string to float.

    Examples:
        '450 €'       -> 450.0
        '1.200 EUR'   -> 1200.0
        '450,50 EUR'  -> 450.5

    This function does not search arbitrary text for a number.
    """
    if price_raw is None or price_raw == "":
        return 0.0

    if isinstance(price_raw, (int, float)):
        return float(price_raw)

    text = str(price_raw).strip()
    text = re.sub(r"(?i)\b(?:EUR|HRK|kn)\b|€", "", text)
    text = text.replace("\u00a0", "").replace(" ", "")

    if not text:
        return 0.0

    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", text):
        text = text.replace(".", "")

    try:
        value = float(text)
        return value if value >= 0 else 0.0
    except ValueError:
        return 0.0


def extract_price(text: Optional[str]) -> Optional[float]:
    """
    Extracts a price only when a supported currency is present.

    A bare number in the title is not treated as a price.
    """
    if not text:
        return None

    number = r"\d(?:[\d.\s\u00a0]*\d)?(?:,\d{1,2})?"

    pattern = re.compile(
        rf"(?<!\w)(?:"
        rf"({number})\s*(?:€|EUR|HRK|kn)"
        rf"|"
        rf"(?:€|EUR|HRK|kn)\s*({number})"
        rf")(?!\w)",
        re.IGNORECASE,
    )

    for match in pattern.finditer(text):
        raw = match.group(1) or match.group(2)
        price = parse_price(raw)

        if price > 0:
            return price

    return None


def parse_area(text: Optional[str]) -> Optional[float]:
    """
    Parses areas such as 45 m2, 45 m², 45,5 m² and 45 kvadrata.
    """
    if not text:
        return None

    pattern = re.compile(
        r"(?<!\d)(\d+(?:[.,]\d+)?)\s*"
        r"(?:m\s*(?:2|²|\^2)|kvm|kvadrat(?:a|nih)?)"
        r"(?!\w)",
        re.IGNORECASE,
    )

    match = pattern.search(text)
    if not match:
        return None

    try:
        area = float(match.group(1).replace(",", "."))
        return area if area > 0 else None
    except ValueError:
        return None


def normalize_url(url: str) -> str:
    """
    Normalizes Facebook URLs and removes query parameters/fragments.

    Returns an empty string for unsupported hosts.
    """
    if not url:
        return ""

    full_url = urllib.parse.urljoin(BASE_URL, url.strip())
    parsed = urllib.parse.urlsplit(full_url)

    host = (parsed.hostname or "").lower()

    if host not in {
        "facebook.com",
        "www.facebook.com",
        "m.facebook.com",
    }:
        return ""

    if parsed.scheme not in {"http", "https"}:
        return ""

    return urllib.parse.urlunsplit(
        (
            "https",
            "www.facebook.com",
            parsed.path.rstrip("/") or "/",
            "",
            "",
        )
    )


def extract_external_id(url: str) -> str:
    """
    Extracts known Facebook listing/post IDs.

    The normalized URL remains the primary deduplication key in the DB.
    """
    patterns = (
        r"/marketplace/item/(\d+)",
        r"/groups/[^/]+/posts/(\d+)",
        r"/groups/[^/]+/permalink/(\d+)",
        r"/posts/(\d+)",
        r"/permalink/(\d+)",
        r"/videos/(\d+)",
    )

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    path = urllib.parse.urlsplit(url).path.rstrip("/")
    return path.rsplit("/", 1)[-1] if path else url


def match_location_id(text: Optional[str]) -> Optional[int]:
    """
    Matches a location against the existing locations table.

    More specific/longer names are checked first.
    """
    if not text:
        return None

    try:
        with get_connectivity() as conn:
            locations = conn.execute(
                "SELECT id, name FROM locations"
            ).fetchall()

        normalized_text = text.casefold()

        for location in sorted(
            locations,
            key=lambda row: len(row["name"] or ""),
            reverse=True,
        ):
            name = (location["name"] or "").strip()
            if not name:
                continue

            if re.search(
                rf"(?<!\w){re.escape(name)}(?!\w)",
                normalized_text,
            ):
                return location["id"]

    except Exception:
        logging.exception("Failed to match Facebook listing location")

    return None


def extract_image_url(container) -> Optional[str]:
    """Extracts an image URL from a listing/post container."""
    if container is None:
        return None

    image = container.find("img")
    if image is None:
        return None

    image_url = image.get("src") or image.get("data-src")

    if not image_url:
        return None

    if image_url.startswith("//"):
        image_url = "https:" + image_url

    if not image_url.startswith("https://"):
        return None

    return image_url


def make_listing(
    url: str,
    text: str,
    source_platform: str,
    image_url: Optional[str] = None,
) -> Optional[Dict]:
    """
    Converts extracted Facebook text into the existing DB listing format.

    Listings without a positive, recognizable price are skipped because
    save_or_update_listing() currently requires float(listing_data["price"]).
    """
    normalized_url = normalize_url(url)

    if not normalized_url or not text:
        return None

    text = re.sub(r"\s+", " ", text).strip()

    if not text or is_listing_text_inactive(text):
        return None

    price = extract_price(text)

    if price is None:
        logging.debug(
            "Skipping listing without a recognizable price: %s",
            normalized_url,
        )
        return None

    price_pattern = re.compile(
        r"(?<!\w)(?:"
        r"\d(?:[\d.,\s\u00a0]*\d)?(?:,\d{1,2})?"
        r"\s*(?:€|EUR|HRK|kn)"
        r"|"
        r"(?:€|EUR|HRK|kn)\s*"
        r"\d(?:[\d.,\s\u00a0]*\d)?(?:,\d{1,2})?"
        r")(?!\w)",
        re.IGNORECASE,
    )

    title = price_pattern.sub("", text, count=1)
    title = title.strip(" \t\r\n-–—|,;:")

    if not title:
        title = "Najam stana u Osijeku"

    title = title[:MAX_TITLE_LENGTH]
    description = text[:MAX_DESCRIPTION_LENGTH]

    if image_url and image_url.startswith("//"):
        image_url = "https:" + image_url

    if image_url and not image_url.startswith("https://"):
        image_url = None

    return {
        "external_id": extract_external_id(normalized_url),
        "source_platform": source_platform,
        "title": title,
        "description": description,
        "price": float(price),
        "area_sqm": parse_area(text),
        "location_id": match_location_id(text),
        "raw_address": "Osijek",
        "url": normalized_url,
        "image_url": image_url,
        "is_active": 1,
    }


def parse_marketplace(soup: BeautifulSoup) -> List[Dict]:
    """
    Parses Marketplace item links from the currently rendered HTML.

    Facebook DOM structures can change, so this parser must be tested
    against the actual HTML returned in the target environment.
    """
    listings: List[Dict] = []
    seen_urls: Set[str] = set()

    links = soup.find_all(
        "a",
        href=lambda href: bool(
            href and "/marketplace/item/" in href
        ),
    )

    for link in links:
        url = normalize_url(link.get("href", ""))

        if not url or url in seen_urls:
            continue

        seen_urls.add(url)

        card_text = link.get_text(separator=" ", strip=True)
        image_url = extract_image_url(link)

        if not card_text:
            continue

        listing = make_listing(
            url=url,
            text=card_text,
            source_platform="Facebook Marketplace",
            image_url=image_url,
        )

        if listing:
            listings.append(listing)

    return listings


def parse_group_posts(soup: BeautifulSoup) -> List[Dict]:
    """
    Parses accessible Facebook group post permalinks.

    This is a best-effort HTML parser, not a guarantee that every post
    or every group is accessible through browser automation.
    """
    listings: List[Dict] = []
    seen_urls: Set[str] = set()

    post_pattern = re.compile(
        r"/groups/[^/]+/(?:posts|permalink)/\d+"
    )

    for link in soup.find_all("a", href=True):
        href = link.get("href", "")

        if not post_pattern.search(href):
            continue

        url = normalize_url(href)

        if not url or url in seen_urls:
            continue

        seen_urls.add(url)

        article = link.find_parent(attrs={"role": "article"})

        text = ""
        image_url = None

        if article is not None:
            text = article.get_text(separator=" ", strip=True)
            image_url = extract_image_url(article)

        parent = link.parent

        for _ in range(6):
            if text and len(text) >= 80:
                break

            if parent is None:
                break

            candidate = parent.get_text(separator=" ", strip=True)

            if 80 <= len(candidate) <= MAX_DESCRIPTION_LENGTH:
                text = candidate
                image_url = image_url or extract_image_url(parent)

            parent = parent.parent

        if not text:
            continue

        listing = make_listing(
            url=url,
            text=text,
            source_platform="Facebook Group",
            image_url=image_url,
        )

        if listing:
            listings.append(listing)

    return listings


async def _scroll_page(page, max_scrolls: int) -> None:
    """Scrolls the current page a bounded number of times."""
    for index in range(max(0, max_scrolls)):
        await page.evaluate("window.scrollBy(0, 900)")
        await page.wait_for_timeout(SCROLL_WAIT_MS)

        logging.debug(
            "Facebook scroll %d/%d",
            index + 1,
            max_scrolls,
        )


async def _scrape_page(
    page,
    url: str,
    source_platform: str,
    max_scrolls: int,
) -> List[Dict]:
    """Loads one Facebook source and dispatches to its parser."""
    try:
        response = await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=NAVIGATION_TIMEOUT_MS,
        )

        if response is not None and response.status >= 400:
            logging.warning(
                "Facebook returned HTTP %s for %s",
                response.status,
                url,
            )
            return []

        await page.wait_for_timeout(INITIAL_WAIT_MS)

        current_url = page.url.lower()

        if (
            "/login" in current_url
            or "/checkpoint" in current_url
            or "/recover" in current_url
        ):
            logging.warning(
                "Facebook login/checkpoint required for %s",
                url,
            )
            return []

        title = (await page.title()).casefold()

        if "log in" in title or "prijavite se" in title:
            logging.warning(
                "Facebook may be showing a login page: %s",
                url,
            )
            return []

        await _scroll_page(page, max_scrolls)

        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        if source_platform == "Facebook Marketplace":
            listings = parse_marketplace(soup)
        else:
            listings = parse_group_posts(soup)

        logging.info(
            "%s: extracted %d listings from %s",
            source_platform,
            len(listings),
            url,
        )

        return listings

    except Exception:
        logging.exception("Failed to scrape Facebook source: %s", url)
        return []


async def scrape_facebook_osijek(
    max_scrolls: int = DEFAULT_MAX_SCROLLS,
) -> List[Dict]:
    """
    Scrapes Marketplace and configured Facebook groups.

    Returns dictionaries compatible with save_or_update_listing().
    Does not write to the DB and does not send Telegram notifications.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logging.error(
            "Playwright is not installed. Install it using: "
            "pip install playwright && playwright install chromium"
        )
        return []

    sources: List[Tuple[str, str]] = [
        (
            MARKETPLACE_OSIJEK_RENTALS_URL,
            "Facebook Marketplace",
        )
    ]

    for group_url in FACEBOOK_GROUP_URLS:
        sources.append((group_url, "Facebook Group"))

    listings: List[Dict] = []
    seen_urls: Set[str] = set()

    logging.info(
        "Starting Facebook scraping: Marketplace + %d groups",
        len(FACEBOOK_GROUP_URLS),
    )

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )

        try:
            context_options = {
                "user_agent": USER_AGENT,
                "viewport": {"width": 1280, "height": 900},
                "locale": "hr-HR",
            }

            if (
                FACEBOOK_STORAGE_STATE
                and os.path.isfile(FACEBOOK_STORAGE_STATE)
            ):
                context_options["storage_state"] = FACEBOOK_STORAGE_STATE

            context = await browser.new_context(**context_options)

            try:
                page = await context.new_page()

                for source_url, platform in sources:
                    logging.info(
                        "Scraping %s: %s",
                        platform,
                        source_url,
                    )

                    page_listings = await _scrape_page(
                        page=page,
                        url=source_url,
                        source_platform=platform,
                        max_scrolls=max_scrolls,
                    )

                    for listing in page_listings:
                        url = listing["url"]

                        if url in seen_urls:
                            continue

                        seen_urls.add(url)
                        listings.append(listing)

            finally:
                await context.close()

        finally:
            await browser.close()

    logging.info(
        "Facebook scraping finished: %d unique listings extracted",
        len(listings),
    )

    return listings


async def run_facebook_scraper_and_save(
    max_scrolls: int = DEFAULT_MAX_SCROLLS,
    app: Optional[Application] = None,
) -> Dict[str, int]:
    """
    Optional standalone workflow.

    Use this OR the Facebook portion of run_pipeline(), not both
    in the same scheduled scraping cycle.
    """
    fetched_listings = await scrape_facebook_osijek(
        max_scrolls=max_scrolls,
    )

    stats = {
        "inserted": 0,
        "exists": 0,
        "price_updated": 0,
        "duplicates": 0,
    }

    for item in fetched_listings:
        try:
            status, listing_id = await asyncio.to_thread(
                save_or_update_listing,
                item,
            )

            if status in ("inserted", "INSERTED"):
                stats["inserted"] += 1

                if app and listing_id:
                    full_item = await asyncio.to_thread(
                        get_listing_by_id,
                        listing_id,
                    )

                    if full_item:
                        await notify_users_about_listing(
                            app,
                            full_item,
                            event_type="inserted",
                        )

            elif status in ("exists", "EXISTS"):
                stats["exists"] += 1

            elif status in (
                "price_drop",
                "PRICE_DROP",
                "price_increased",
                "price_updated",
            ):
                stats["price_updated"] += 1

                if (
                    app
                    and listing_id
                    and status in ("price_drop", "PRICE_DROP")
                ):
                    full_item = await asyncio.to_thread(
                        get_listing_by_id,
                        listing_id,
                    )

                    if full_item:
                        full_item["old_price"] = item.get("old_price")

                        await notify_users_about_listing(
                            app,
                            full_item,
                            event_type="price_drop",
                        )

            elif status in (
                "duplicate_cross_post",
                "DUPLICATE_CROSS_POST",
            ):
                stats["duplicates"] += 1

        except Exception:
            logging.exception(
                "Failed to save/process Facebook listing: %s",
                item.get("url"),
            )

    logging.info("Facebook save statistics: %s", stats)
    return stats
