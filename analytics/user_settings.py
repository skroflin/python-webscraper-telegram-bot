import logging
from typing import Optional, Dict
from database.database import get_connectivity


def set_user_budget(telegram_id: int, first_name: str, max_price: float) -> bool:
    try:
        with get_connectivity() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (telegram_id, first_name, max_price)
                VALUES (?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    max_price = excluded.max_price,
                    first_name = excluded.first_name
            """, (telegram_id, first_name, max_price))
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"\U0001F506 Error setting budget for user {telegram_id}: {e}")
        return False


def set_user_min_area(telegram_id: int, first_name: str, min_area: float) -> bool:
    try:
        with get_connectivity() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (telegram_id, first_name, min_area)
                VALUES (?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    min_area = excluded.min_area,
                    first_name = excluded.first_name
            """, (telegram_id, first_name, min_area))
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"\U0001F506 Error setting area for user {telegram_id}: {e}")
        return False


def get_user_profile(telegram_id: int) -> Optional[Dict]:
    try:
        with get_connectivity() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT max_price, min_area FROM users WHERE telegram_id = ?", (telegram_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as e:
        logging.error(f"\U0001F506 Error fetching profile for user {telegram_id}: {e}")
        return None


def reset_user_filters(telegram_id: int) -> bool:
    try:
        with get_connectivity() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users 
                SET max_price = NULL, min_area = NULL 
                WHERE telegram_id = ?
            """, (telegram_id,))
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"\U0001F506 Error resetting filters for user {telegram_id}: {e}")
        return False

def save_listing(telegram_id: int, first_name: str, listing_id: int) -> bool:
    try:
        with get_connectivity() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (telegram_id, first_name)
                VALUES (?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET first_name = excluded.first_name
            """, (telegram_id, first_name))
            
            cursor.execute("""
                INSERT OR IGNORE INTO saved_listings (user_id, listing_id)
                VALUES (?, ?)
            """, (telegram_id, listing_id))
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"\u274c Error saving listing {listing_id} for user {telegram_id}: {e}")
        return False


def remove_saved_listing(telegram_id: int, listing_id: int) -> bool:
    try:
        with get_connectivity() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM saved_listings 
                WHERE user_id = ? AND listing_id = ?
            """, (telegram_id, listing_id))
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"\u274c Error removing listing {listing_id} for user {telegram_id}: {e}")
        return False


def get_saved_listings(telegram_id: int) -> list:
    try:
        with get_connectivity() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT l.id, l.title, l.price, l.area_sqm, l.source_platform, l.url
                FROM listings l
                JOIN saved_listings sl ON l.id = sl.listing_id
                WHERE sl.user_id = ?
                ORDER BY sl.saved_at DESC
            """, (telegram_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logging.error(f"\u274c Error fetching saved listings for user {telegram_id}: {e}")
        return []

def add_user_neighborhood(telegram_id: int, first_name: str, neighborhood_name: str) -> tuple[bool, str]:
    """Adding neihborhood to user preferences."""
    try:
        with get_connectivity() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO users (telegram_id, first_name)
                VALUES (?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET first_name = excluded.first_name
            """, (telegram_id, first_name))
            
            cursor.execute("SELECT id, name FROM locations WHERE LOWER(name) = LOWER(?)", (neighborhood_name.strip(),))
            loc = cursor.fetchone()

            if not loc:
                return False, f"Kvart **'{neighborhood_name}'** nije pronađen u bazi."
            
            cursor.execute("""
                INSERT OR IGNORE INTO user_locations (user_id, location_id)
                VALUES (?, ?)
            """, (telegram_id, loc["id"]))
            conn.commit()

            return True, loc["name"]
    except Exception as e:
        logging.error(f"Error adding neighborhood for user {telegram_id}: {e}")
        return False, "Greška pri upisu u bazu."


def remove_user_neighborhood(telegram_id: int, neighborhood_name: str) -> tuple[bool, str]:
    """Removing neighborhood from user preferences."""
    try:
        with get_connectivity() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM user_locations
                WHERE user_id = ? AND location_id IN (
                    SELECT id FROM locations WHERE LOWER(name) = LOWER(?)
                )
            """, (telegram_id, neighborhood_name.strip()))
            
            if cursor.rowcount > 0:
                conn.commit()
                return True, neighborhood_name
            return False, f"Kvart **'{neighborhood_name}'** nije bio na vašoj listi."
    except Exception as e:
        logging.error(f"Error removing neighborhood for user {telegram_id}: {e}")
        return False, "Greška pri brisanju iz baze."


def get_user_neighborhoods(telegram_id: int) -> list[str]:
    """Getting user neighborhoods from database."""
    try:
        with get_connectivity() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT l.name 
                FROM locations l
                JOIN user_locations ul ON l.id = ul.location_id
                WHERE ul.user_id = ?
                ORDER BY l.name ASC
            """, (telegram_id,))
            rows = cursor.fetchall()
            return [row["name"] for row in rows]
    except Exception as e:
        logging.error(f"Error fetching neighborhoods for user {telegram_id}: {e}")
        return []

def get_all_locations() -> list[dict]:
    """Fetching all available neighborhoods from db ordered by name."""
    try:
        with get_connectivity() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name FROM locations ORDER BY name ASC")
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logging.error(f"Error fetching all locations: {e}")
        return []


def get_user_location_ids(telegram_id: int) -> set[int]:
    """Fetching set of location ids that user currently follows."""
    try:
        with get_connectivity() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT location_id FROM user_locations WHERE user_id = ?", (telegram_id,))
            return {row["location_id"] for row in cursor.fetchall()}
    except Exception as e:
        logging.error(f"Error fetching user location IDs: {e}")
        return set()


def toggle_user_neighborhood_by_id(telegram_id: int, location_id: int) -> bool:
    """Turning on or off the neighborhood from the user's list. Returns `True` if added, `False` if removed."""
    try:
        with get_connectivity() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM user_locations WHERE user_id = ? AND location_id = ?",
                (telegram_id, location_id)
            )
            exists = cursor.fetchone()

            if exists:
                cursor.execute(
                    "DELETE FROM user_locations WHERE user_id = ? AND location_id = ?",
                    (telegram_id, location_id)
                )
                conn.commit()
                return False
            else:
                cursor.execute(
                    "INSERT INTO user_locations (user_id, location_id) VALUES (?, ?)",
                    (telegram_id, location_id)
                )
                conn.commit()
                return True
    except Exception as e:
        logging.error(f"Error toggling neighborhood id {location_id} for user {telegram_id}: {e}")
        return False