import hashlib
import os
import sqlite3
from difflib import SequenceMatcher
from typing import Dict, Optional, Tuple
from config import DB_PATH

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def text_similarity(str1: str, str2: str) -> float:
    if not str1 or not str2:
        return 0.0
    return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()


def find_cross_post_duplicate(cursor, listing_data: Dict) -> Optional[int]:
    price = float(listing_data["price"])
    area = listing_data.get("area_sqm")
    title = listing_data["title"]
    location_id = listing_data.get("location_id")
    platform = listing_data.get("source_platform")

    min_price, max_price = price * 0.95, price * 1.05

    cursor.execute("""
        SELECT id, title, price, area_sqm, location_id, source_platform
        FROM listings
        WHERE is_active = 1
          AND price BETWEEN ? AND ?
          AND source_platform != ?
    """, (min_price, max_price, platform))

    candidates = cursor.fetchall()

    for cand in candidates:
        cand_area = cand["area_sqm"]
        if area and cand_area:
            if abs(area - cand_area) > 3.0:
                continue

        cand_loc = cand["location_id"]
        if location_id and cand_loc and location_id != cand_loc:
            continue

        sim_score = text_similarity(title, cand["title"])
        if sim_score >= 0.75:
            return cand["id"]

    return None


def get_connectivity(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _apply_schema(conn: sqlite3.Connection, schema_sql: str) -> None:
    base_schema, migration_marker, migrations = schema_sql.partition("-- @migrations")
    conn.executescript(base_schema)

    if not migration_marker:
        return

    for statement in migrations.split(";"):
        statement = statement.strip()
        if not statement:
            continue

        try:
            conn.execute(statement)
        except sqlite3.OperationalError as error:
            if "duplicate column name" not in str(error).lower():
                raise


def init_db(schema_file: str = "database/schema.sql", db_path: str = DB_PATH) -> None:
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    if not os.path.exists(schema_file):
        raise FileNotFoundError(f"SQL script: {schema_file} not found \U0001F625")

    with open(schema_file, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    with get_connectivity(db_path) as conn:
        _apply_schema(conn, schema_sql)


def generate_content_hash(title: str, price: float, area_sqm: Optional[float]) -> str:
    normalized_title = "".join(title.lower().split())
    area_str = str(round(area_sqm, 1)) if area_sqm else "0"
    raw_data = f"{normalized_title}_{price}_{area_str}"
    return hashlib.sha256(raw_data.encode("utf-8")).hexdigest()


def save_or_update_listing(listing_data: Dict, db_path: str = DB_PATH) -> Tuple[str, Optional[int]]:
    url = listing_data["url"]
    price = float(listing_data["price"])
    title = listing_data["title"]
    area_sqm = listing_data.get("area_sqm")

    content_hash = generate_content_hash(title, price, area_sqm)

    with get_connectivity(db_path) as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT id, price FROM listings WHERE url = ?", (url,))
        existing_url = cursor.fetchone()

        if existing_url:
            listing_id, old_price = existing_url["id"], existing_url["price"]

            if old_price != price:
                cursor.execute(
                    "UPDATE listings SET price = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (price, listing_id)
                )
                cursor.execute(
                    "INSERT INTO price_history (listing_id, old_price, new_price) VALUES (?, ?, ?)",
                    (listing_id, old_price, price)
                )
                conn.commit()

                listing_data["old_price"] = old_price
                listing_data["id"] = listing_id

                if price < old_price:
                    return "price_drop", listing_id
                else:
                    return "price_increased", listing_id

            return "exists", listing_id

        duplicate_id = find_cross_post_duplicate(cursor, listing_data)
        if duplicate_id:
            return "duplicate_cross_post", duplicate_id

        sql_insert = """
            INSERT INTO listings (
                external_id, source_platform, title, description, price,
                area_sqm, location_id, raw_address, url, image_url, content_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        cursor.execute(sql_insert, (
            listing_data.get("external_id"),
            listing_data["source_platform"],
            title,
            listing_data.get("description"),
            price,
            area_sqm,
            listing_data.get("location_id"),
            listing_data.get("raw_address"),
            url,
            listing_data.get("image_url"),
            content_hash
        ))
        conn.commit()
        return "inserted", cursor.lastrowid

def get_listing_by_id(listing_id: int) -> Optional[Dict]:
    try:
        with get_connectivity() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    l.id, l.title, l.description, l.price, l.area_sqm, 
                    l.source_platform, l.url, l.image_url, l.location_id,
                    loc.name AS neighborhood, loc.latitude, loc.longitude
                FROM listings l
                LEFT JOIN locations loc ON l.location_id = loc.id
                WHERE l.id = ?
            """, (listing_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as e:
        logging.error(f"Error fetching listing {listing_id}: {e}")
        return None