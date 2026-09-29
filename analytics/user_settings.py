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