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