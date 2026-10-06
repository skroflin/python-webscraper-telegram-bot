import logging
from typing import Dict, List, Optional
from database.database import get_connectivity
from analytics.poi import calculate_distance_km


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
                WHERE is_active = 1
            """)
            stats = cursor.fetchone()
            return dict(stats) if stats else None
    except Exception as e:
        logging.error(f"\U0001F506 Error fetching market analytics: {e}")
        return None


def get_best_buy_listings(limit: int = 3) -> list[dict]:
    """Dohvaća najpovoljnije stanove po m^2 s prikazom kvarta, adrese i koordinata za POI."""
    try:
        with get_connectivity() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    l.id, l.title, l.price, l.area_sqm, l.source_platform, 
                    l.url, l.image_url, l.description, l.raw_address,
                    loc.name AS neighborhood, loc.latitude, loc.longitude,
                    (l.price / l.area_sqm) AS price_per_sqm
                FROM listings l
                LEFT JOIN locations loc ON l.location_id = loc.id
                WHERE l.is_active = 1 AND l.area_sqm IS NOT NULL AND l.area_sqm > 0
                ORDER BY price_per_sqm ASC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logging.error(f"Error fetching best buy listings: {e}")
        return []


def get_latest_listings(limit: int = 5) -> List[Dict]:
    try:
        with get_connectivity() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, price, area_sqm, source_platform, url
                FROM listings
                WHERE is_active = 1
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logging.error(f"\U0001F506 Error fetching latest listings: {e}")
        return []


def get_listings_near_location(latitude: float, longitude: float, radius_km: float) -> List[Dict]:
    try:
        with get_connectivity() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    l.id, l.title, l.description, l.price, l.area_sqm,
                    l.source_platform, l.url, l.image_url, l.location_id,
                    loc.name AS neighborhood, loc.latitude, loc.longitude
                FROM listings l
                JOIN locations loc ON l.location_id = loc.id
                WHERE l.is_active = 1
                  AND loc.latitude IS NOT NULL
                  AND loc.longitude IS NOT NULL
            """)
            listings = []
            for row in cursor.fetchall():
                item = dict(row)
                item["distance_km"] = calculate_distance_km(
                    latitude, longitude, item["latitude"], item["longitude"]
                )
                if item["distance_km"] <= radius_km:
                    listings.append(item)

            return sorted(listings, key=lambda item: item["distance_km"])
    except Exception as e:
        logging.error(f"Error fetching nearby listings: {e}")
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
                WHERE l.is_active = 1 AND l.price > 0
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