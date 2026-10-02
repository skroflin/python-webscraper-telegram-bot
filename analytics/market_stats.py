import logging
from typing import Dict, List, Optional
from database.database import get_connectivity


def get_market_analytics() -> Optional[Dict]:
    try:
        with get_connectivity() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    AVG(price) as avg_price,
                    AVG(price / NULLIF(area_sqm, 0)) as avg_sqm_price
                FROM listings
            """)
            stats = cursor.fetchone()
            return dict(stats) if stats else None
    except Exception as e:
        logging.error(f"\U0001F506 Error fetching market analytics: {e}")
        return None


def get_best_buy_listings(limit: int = 3) -> List[Dict]:
    try:
        with get_connectivity() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, price, area_sqm, (price / area_sqm) as price_per_sqm, url
                FROM listings
                WHERE area_sqm IS NOT NULL AND area_sqm > 0 AND price > 0
                ORDER BY price_per_sqm ASC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logging.error(f"\U0001F506 Error fetching best buy listings: {e}")
        return []


def get_latest_listings(limit: int = 5) -> List[Dict]:
    try:
        with get_connectivity() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, price, area_sqm, source_platform, url
                FROM listings
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logging.error(f"\U0001F506 Error fetching latest listings: {e}")
        return []

def get_neighborhood_stats() -> List[Dict]:
    try:
        with get_connectivity() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    loc.name as neighborhood,
                    COUNT(l.id) as total_listings,
                    AVG(l.price) as avg_price,
                    AVG(l.price / NULLIF(l.area_sqm, 0)) as avg_sqm_price
                FROM locations loc
                JOIN listings l ON loc.id = l.location_id
                WHERE l.price > 0
                GROUP BY loc.id, loc.name
                HAVING total_listings > 0
                ORDER BY avg_price DESC
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logging.error(f"\U0001F506 Error fetching neighborhood stats: {e}")
        return []

def get_listings_by_neighborhood(neighborhood_name: str, limit: int = 5) -> List[Dict]:
    try:
        with get_connectivity() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT l.title, l.price, l.area_sqm, l.source_platform, l.url, loc.name as neighborhood
                FROM listings l
                JOIN locations loc ON l.location_id = loc.id
                WHERE LOWER(loc.name) = LOWER(?) AND l.is_active = 1
                ORDER BY l.created_at DESC
                LIMIT ?
            """, (neighborhood_name.strip(), limit))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logging.error(f"\U0001F506 Error fetching listings for neighborhood {neighborhood_name}: {e}")
        return []