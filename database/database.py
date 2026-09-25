import hashlib
import os
import sqlite3
from typing import Dict, Optional, Tuple
from config import DB_PATH

def get_connectivity(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Return connection to SQLite db with enabled foreign keys."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db(schema_file: str = "database/schema.sql", db_path: str = DB_PATH) -> None:
    """Initialize db and create tables from .sql script file."""
    if not os.path.exists(schema_file):
        raise FileNotFoundError(f"SQL script: {schema_file} not found \U0001F625")

    with open(schema_file, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    with get_connectivity(db_path) as conn:
        conn.executescript(schema_sql)

def generate_content_hash(title: str, price: float, area_sqm: Optional[float]) -> str:
    """Generating sha-256 hash for cross-duplicate detection."""
    normalized_title = "".join(title.lower().split())
    area_str = str(round(area_sqm, 1)) if area_sqm else "0"
    raw_data = f"{normalized_title}_{price}_{area_str}"
    return hashlib.sha256(raw_data.encode("utf-8")).hexdigest()

def save_or_update_listing(listing_data: Dict, db_path: str = DB_PATH) -> Tuple[str, Optional[int]]:
    """Saving new posting or updating existing if there is a price change."""
    url = listing_data["url"]
    price = float(listing_data["price"])
    title = listing_data["title"]
    area_sqm = listing_data.get("area_sqm")

    content_hash = generate_content_hash(title, price, area_sqm)

    with get_connectivity(db_path) as conn:
        cursor = conn.cursor()

        cursor.execute("select id, price from listings where url = ?", (url,))
        existing_url = cursor.fetchone()

        if existing_url:
            listing_id, old_price = existing_url["id"], existing_url["price"]

            if old_price != price:
                cursor.execute(
                    "update listings set price = ?, updated_at = current_timestamp where id = ?",
                    (price, listing_id)
                )
                cursor.execute(
                    "insert into price_history (listing_id, old_price, new_price) values (?, ?, ?)",
                    (listing_id, old_price, price)
                )
                conn.commit()
                return "price_updated", listing_id

            return "exists", listing_id

        cursor.execute("select id from listings where content_hash = ? and is_active = 1", (content_hash,))
        existing_hash = cursor.fetchone()
        if existing_hash:
            return "duplicate_cross_point", existing_hash["id"]

        sql_insert = """
            insert into listings (
                external_id, source_platform, title, description, price,
                area_sqm, location_id, raw_address, url, content_hash
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            content_hash
        ))
        conn.commit()
        return "inserted", cursor.lastrowid