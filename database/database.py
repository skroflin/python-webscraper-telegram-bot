import hashlib
import os
import sqlite3
from difflib import SequenceMatcher
from typing import Dict, Optional, Tuple
from config import DB_PATH


OSIJEK_POI_SEED = [
    {"key_name": "portanova", "name": "TC Portanova", "category": "shopping", "lat": 45.5615, "lon": 18.6280},
    {"key_name": "mall_osijek", "name": "Mall Osijek", "category": "shopping", "lat": 45.5418, "lon": 18.7088},
    {"key_name": "konzum_super_svacicova", "name": "Super Konzum (Svačićeva)", "category": "supermarket", "lat": 45.5528, "lon": 18.6945},
    {"key_name": "konzum_centar", "name": "Konzum Centar (Trg)", "category": "supermarket", "lat": 45.5605, "lon": 18.6792},
    {"key_name": "konzum_retfala", "name": "Konzum (Retfala / Strossmayerova)", "category": "supermarket", "lat": 45.5618, "lon": 18.6520},
    {"key_name": "interspar_dakovstina", "name": "Interspar (Đakovština)", "category": "supermarket", "lat": 45.5525, "lon": 18.6705},
    {"key_name": "interspar_retfala", "name": "Interspar (Retfala)", "category": "supermarket", "lat": 45.5622, "lon": 18.6435},
    {"key_name": "lidl_retfala", "name": "Lidl (Retfala)", "category": "supermarket", "lat": 45.5620, "lon": 18.6410},
    {"key_name": "lidl_svacicova", "name": "Lidl (Svačićeva / Kampus)", "category": "supermarket", "lat": 45.5515, "lon": 18.6990},
    {"key_name": "lidl_donji_grad", "name": "Lidl (Donji Grad)", "category": "supermarket", "lat": 45.5565, "lon": 18.7250},
    {"key_name": "kaufland_retfala", "name": "Kaufland (Retfala)", "category": "supermarket", "lat": 45.5625, "lon": 18.6480},
    {"key_name": "eurospin_gacka", "name": "Eurospin (Gacka)", "category": "supermarket", "lat": 45.5450, "lon": 18.6930},
    {"key_name": "plodine_huttlerova", "name": "Plodine (Huttlerova)", "category": "supermarket", "lat": 45.5505, "lon": 18.7180},
    {"key_name": "kbc_bolnica", "name": "KBC Osijek (Bolnica)", "category": "health", "lat": 45.5582, "lon": 18.7115},
    {"key_name": "dom_zdravlja_centar", "name": "Dom zdravlja Centar", "category": "health", "lat": 45.5590, "lon": 18.6870},
    {"key_name": "dom_zdravlja_retfala", "name": "Dom zdravlja Retfala", "category": "health", "lat": 45.5610, "lon": 18.6490},
    {"key_name": "dom_zdravlja_donji_grad", "name": "Dom zdravlja Donji Grad", "category": "health", "lat": 45.5595, "lon": 18.7220},
    {"key_name": "dom_zdravlja_jug2", "name": "Dom zdravlja Jug 2", "category": "health", "lat": 45.5410, "lon": 18.7140},
    {"key_name": "dom_zdravlja_industrial", "name": "Dom zdravlja Industrijska", "category": "health", "lat": 45.5435, "lon": 18.6770},
    {"key_name": "kampus_faks", "name": "Sveučilišni kampus", "category": "education", "lat": 45.5542, "lon": 18.7032},
    {"key_name": "ffos", "name": "Filozofski fakultet (FFOS)", "category": "education", "lat": 45.5574, "lon": 18.6806},
    {"key_name": "efos", "name": "Ekonomski fakultet (EFOS)", "category": "education", "lat": 45.5570, "lon": 18.6850},
    {"key_name": "pravos", "name": "Pravni fakultet (PRAVOS)", "category": "education", "lat": 45.5560, "lon": 18.6810},
    {"key_name": "ferit_trpimirova", "name": "FERIT (Trpimirova)", "category": "education", "lat": 45.5535, "lon": 18.7025},
    {"key_name": "mefos", "name": "Medicinski fakultet (MEFOS)", "category": "education", "lat": 45.5585, "lon": 18.7120},
    {"key_name": "gradnos", "name": "Građevinski i arhitektonski (GRADNOS)", "category": "education", "lat": 45.5540, "lon": 18.7040},
    {"key_name": "autobusni_kolodvor", "name": "Autobusni kolodvor", "category": "transport", "lat": 45.5528, "lon": 18.6758},
    {"key_name": "zeljeznicki_kolodvor", "name": "Željeznički kolodvor", "category": "transport", "lat": 45.5522, "lon": 18.6765},
    {"key_name": "centar_trg", "name": "Trg Ante Starčevića", "category": "landmark", "lat": 45.5601, "lon": 18.6789},
    {"key_name": "tvrda", "name": "Tvrđa", "category": "landmark", "lat": 45.5610, "lon": 18.6960},
    {"key_name": "opus_arena", "name": "Opus Arena (Pampas)", "category": "sports", "lat": 45.5650, "lon": 18.6380},
    {"key_name": "gradski_vrt", "name": "Dvorana / Stadion Gradski vrt", "category": "sports", "lat": 45.5445, "lon": 18.6970},
    {"key_name": "copacabana", "name": "Copacabana (Kopa)", "category": "recreation", "lat": 45.5670, "lon": 18.6820},
]


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


def init_db(schema_file: str = "database/schema.sql", db_path: str = DB_PATH) -> None:
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    if not os.path.exists(schema_file):
        raise FileNotFoundError(f"SQL script: {schema_file} not found \U0001F625")

    with open(schema_file, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    with get_connectivity(db_path) as conn:
        cursor = conn.cursor()
        
        conn.executescript(schema_sql)

        try:
            cursor.execute("ALTER TABLE listings ADD COLUMN image_url TEXT;")
            conn.commit()
        except sqlite3.OperationalError:
            pass

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_locations (
                user_id INTEGER NOT NULL,
                location_id INTEGER NOT NULL,
                PRIMARY KEY (user_id, location_id),
                FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE,
                FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE CASCADE
            );
        """)
        conn.commit()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_saved_listings (
                user_id INTEGER NOT NULL,
                listing_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, listing_id),
                FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE,
                FOREIGN KEY (listing_id) REFERENCES listings(id) ON DELETE CASCADE
            );
        """)
        conn.commit()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pois (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_name TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL
            );
        """)
        conn.commit()

        cursor.execute("SELECT COUNT(*) as count FROM pois")
        if cursor.fetchone()["count"] == 0:
            cursor.executemany("""
                INSERT INTO pois (key_name, name, category, latitude, longitude)
                VALUES (:key_name, :name, :category, :lat, :lon)
            """, OSIJEK_POI_SEED)
            conn.commit()


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