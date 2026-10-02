import logging
import requests
from typing import Tuple
from config import DB_PATH
from database.database import get_connectivity

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    )
}


def check_listing_url_status(url: str, source_platform: str) -> bool:
    """
    Sječe HTTP zahtjev na URL oglasa i provjerava je li oglas još aktivan.
    Vraća `True` ako je oglas aktivan, `False` ako vrati 404/grešku ili preusmjeri na naslovnicu.
    """
    try:
        response = requests.head(url, headers=HEADERS, timeout=8, allow_redirects=True)
        if response.status_code in (405, 403):
            response = requests.get(url, headers=HEADERS, timeout=8, allow_redirects=True, stream=True)

        if response.status_code in (404, 410):
            return False

        if response.status_code >= 400:
            return False

        final_url = response.url.lower()

        if "njuskalo" in source_platform.lower():
            if final_url in ("https://www.njuskalo.hr/", "https://www.njuskalo.hr"):
                return False
            if "/iznajmljivanje-stanova" in final_url and not any(char.isdigit() for char in final_url.split("/")[-1]):
                return False

        if "index" in source_platform.lower():
            if final_url.rstrip("/") in ("https://www.index.hr/oglasi", "https://www.index.hr"):
                return False

        return True

    except requests.RequestException as e:
        logging.warning(f"Health check request failed for {url}: {e}")
        return True


def run_health_check(db_path: str = DB_PATH) -> Tuple[int, int]:
    """
    Prolazi kroz sve aktivne oglase i ažurira is_active status u bazi.
    Vraća (`ukupno_provjereno`, `ukupno_deaktivirano`).
    """
    logging.info("\U0001F9F9 Pokrećem Health Check za aktivne oglase...")

    with get_connectivity(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, url, source_platform FROM listings WHERE is_active = 1")
        active_listings = cursor.fetchall()

        if not active_listings:
            logging.info("\U0001F9F9 Nema aktivnih oglasa za provjeru.")
            return 0, 0

        checked_count = 0
        deactivated_count = 0

        for row in active_listings:
            listing_id = row["id"]
            url = row["url"]
            platform = row["source_platform"]
            title = row["title"]

            is_still_active = check_listing_url_status(url, platform)
            checked_count += 1

            if not is_still_active:
                cursor.execute(
                    "UPDATE listings SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (listing_id,)
                )
                conn.commit()
                deactivated_count += 1
                logging.info(f"\U0001F44C Deaktiviran oglas #{listing_id}: {title} ({url})")

        logging.info(f"\U0001F504 Health Check završen: provjereno {checked_count}, deaktivirano {deactivated_count} oglasa.")
        return checked_count, deactivated_count