import logging
import requests
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Tuple
from config import DB_PATH
from database.database import get_connectivity

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    )
}


def check_listing_url_status(url: str, source_platform: str) -> Optional[bool]:
    """
    Sječe HTTP zahtjev na URL oglasa i provjerava je li oglas još aktivan.
    Vraća `None` kad HTTP odgovor ne omogućuje pouzdan zaključak.
    """
    response = None
    try:
        response = requests.head(url, headers=HEADERS, timeout=8, allow_redirects=True)
        if response.status_code in (405, 403):
            response.close()
            response = requests.get(url, headers=HEADERS, timeout=8, allow_redirects=True, stream=True)

        if response.status_code in (404, 410):
            return False

        if response.status_code >= 400:
            return None

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
        return None
    finally:
        if response is not None:
            response.close()


def run_health_check(db_path: str = DB_PATH, max_workers: int = 8) -> Tuple[int, int]:
    """
    Prolazi kroz sve aktivne oglase i ažurira is_active status u bazi.
    Vraća (`ukupno_provjereno`, `ukupno_deaktivirano`).
    """
    logging.info("\U0001F9F9 Pokrećem Health Check za aktivne oglase...")

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
        "\U0001F504 Health Check završen: provjereno %s, deaktivirano %s oglasa.",
        len(active_listings), len(deactivated),
    )
    return len(active_listings), len(deactivated)