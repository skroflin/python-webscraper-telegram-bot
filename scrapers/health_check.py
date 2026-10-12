import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Tuple
from bs4 import BeautifulSoup
import requests
from config import DB_PATH
from database.database import get_connectivity

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "hr-HR,hr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Ch-Ua": '"Chromium";v="128", "Not=A?Brand";v="24", "Google Chrome";v="128"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

INACTIVE_PHRASES = (
    "oglas je neaktivan",
    "ovaj oglas je neaktivan",
    "oglas je prodan",
    "ovaj oglas je prodan",
    "oglas je iznajmljen",
    "ovaj oglas je iznajmljen",
    "oglas je istekao",
    "ovaj oglas je istekao",
    "korisnik je deaktivirao oglas",
    "oglas više nije aktivan",
    "oglas vise nije aktivan",
    "ovaj oglas više nije dostupan",
    "ovaj oglas vise nije dostupan",
    "stan je iznajmljen",
)

INACTIVE_TITLE_PATTERNS = (
    r"\bprodano\b",
    r"\bprodan\b",
    r"\biznajmljeno\b",
    r"\biznajmljen\b",
    r"\brezervirano\b",
    r"\brezerviran\b",
    r"\bkapareno\b",
    r"\bkaparen\b",
    r"\bneaktivno\b",
    r"\bneaktivan\b",
    r"\bisteklo\b",
    r"\bistekao\b",
    r"\bzakupljeno\b",
    r"\bzakupljen\b",
)

_thread_local = threading.local()


def is_listing_text_inactive(text: Optional[str]) -> bool:
    if not text:
        return False
    lower_text = text.lower()
    for phrase in INACTIVE_PHRASES:
        if phrase in lower_text:
            return True
    for pattern in INACTIVE_TITLE_PATTERNS:
        if re.search(pattern, lower_text, re.IGNORECASE):
            return True
    return False


def check_listing_url_status(url: str, source_platform: str) -> Optional[bool]:
    source_lower = (source_platform or "").lower().replace("\u0161", "s").replace("\u010d", "c").replace("\u0107", "c")
    response = None
    try:
        response = requests.head(url, headers=HEADERS, timeout=8, allow_redirects=True)
        if response.status_code in (405, 403):
            if hasattr(response, "close"):
                response.close()
            response = requests.get(url, headers=HEADERS, timeout=8, allow_redirects=True, stream=True)

        if response.status_code in (404, 410):
            return False

        if response.status_code >= 400:
            return None

        final_url = response.url.lower()

        if "njuskalo" in source_lower:
            if final_url in ("https://www.njuskalo.hr/", "https://www.njuskalo.hr"):
                return False
            if "/iznajmljivanje-stanova" in final_url and not any(char.isdigit() for char in final_url.split("/")[-1]):
                return False

            req_headers = {
                **HEADERS,
                "Referer": "https://www.njuskalo.hr/iznajmljivanje-stanova/osijek",
            }
            resp_get = requests.get(url, headers=req_headers, timeout=8, allow_redirects=True)
            if resp_get.status_code in (404, 410):
                return False
            if resp_get.status_code >= 400:
                return None
            final_get_url = resp_get.url.lower()
            if final_get_url in ("https://www.njuskalo.hr/", "https://www.njuskalo.hr"):
                return False
            if "/iznajmljivanje-stanova" in final_get_url and not any(char.isdigit() for char in final_get_url.split("/")[-1]):
                return False
            if "validate.perfdrive.com" in final_get_url:
                return None
            soup = BeautifulSoup(resp_get.text, "html.parser")
            if soup.title and "shieldsquare captcha" in soup.title.get_text().lower():
                return None
            if soup.select(".ClassifiedDetailUnavailableNotice, [class*='UnavailableNotice']"):
                return False
            if is_listing_text_inactive(resp_get.text):
                return False
            return True

        if "index" in source_lower:
            if final_url.rstrip("/") in ("https://www.index.hr/oglasi", "https://www.index.hr"):
                return False
            code_match = re.search(r"/(\d+)(?:\.aspx)?$", url)
            if code_match:
                try:
                    code = int(code_match.group(1))
                    api_headers = {
                        **HEADERS,
                        "Accept": "application/json, text/plain, */*",
                        "Referer": url,
                        "X-Requested-With": "XMLHttpRequest",
                    }
                    api_resp = requests.get(
                        "https://www.index.hr/oglasi/api/aditem/single-ad",
                        headers=api_headers,
                        params={"code": code},
                        timeout=8,
                    )
                    if api_resp.status_code == 404:
                        return False
                    if api_resp.status_code == 200:
                        data = api_resp.json()
                        items = data.get("data", [])
                        if not items:
                            return False
                        status = items[0].get("status")
                        if status is not None and status != 1:
                            return False
                        title = items[0].get("title") or ""
                        if is_listing_text_inactive(title):
                            return False
                        return True
                except Exception:
                    pass

            resp_get = requests.get(url, headers=HEADERS, timeout=8, allow_redirects=True)
            if resp_get.status_code in (404, 410):
                return False
            if resp_get.status_code >= 400:
                return None
            final_get_url = resp_get.url.lower().rstrip("/")
            if final_get_url in ("https://www.index.hr/oglasi", "https://www.index.hr"):
                return False
            if is_listing_text_inactive(resp_get.text):
                return False
            return True

        return True

    except requests.RequestException as e:
        logging.warning("Health check request failed for %s: %s", url, e)
        return None
    finally:
        if response is not None and hasattr(response, "close"):
            response.close()


def run_health_check(db_path: str = DB_PATH, max_workers: int = 8) -> Tuple[int, int]:
    logging.info("\U0001F9F9 Pokre\u0107em Health Check za aktivne oglase...")

    if max_workers < 1:
        raise ValueError("max_workers must be at least 1")

    with get_connectivity(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, url, source_platform FROM listings WHERE is_active = 1")
        active_listings = cursor.fetchall()

        if not active_listings:
            logging.info("\U0001F9F9 Nema aktivnih oglasa za provjeru.")
            return 0, 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        statuses = list(executor.map(
            lambda row: check_listing_url_status(row["url"], row["source_platform"]),
            active_listings,
        ))

    deactivated = [
        row for row, status in zip(active_listings, statuses)
        if status is False
    ]
    if deactivated:
        with get_connectivity(db_path) as conn:
            conn.executemany(
                "UPDATE listings SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                [(row["id"],) for row in deactivated],
            )
            conn.commit()

    for row in deactivated:
        logging.info("\U0001F44C Deaktiviran oglas #%s: %s (%s)", row["id"], row["title"], row["url"])

    logging.info(
        "\U0001F504 Health Check zavr\u0161en: provjereno %s, deaktivirano %s oglasa.",
        len(active_listings), len(deactivated),
    )
    return len(active_listings), len(deactivated)