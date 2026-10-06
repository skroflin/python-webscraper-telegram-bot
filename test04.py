import sqlite3
from pathlib import Path

from analytics.market_stats import get_listings_near_location


def test_get_listings_near_location_filters_and_sorts(monkeypatch):
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE locations (id INTEGER PRIMARY KEY, name TEXT, latitude REAL, longitude REAL);
        CREATE TABLE listings (
            id INTEGER PRIMARY KEY, title TEXT, description TEXT, price REAL, area_sqm REAL,
            source_platform TEXT, url TEXT, image_url TEXT, location_id INTEGER, is_active INTEGER
        );
        INSERT INTO locations VALUES (1, 'Centar', 45.0, 18.0);
        INSERT INTO locations VALUES (2, 'Retfala', 45.0, 18.05);
        INSERT INTO locations VALUES (3, 'Sjenjak', 45.0, 18.01);
        INSERT INTO listings VALUES (1, 'Centar stan', '', 400, 50, 'Test', 'https://example.com/1', NULL, 1, 1);
        INSERT INTO listings VALUES (2, 'Retfala stan', '', 450, 55, 'Test', 'https://example.com/2', NULL, 2, 1);
        INSERT INTO listings VALUES (3, 'Sjenjak stan', '', 420, 52, 'Test', 'https://example.com/3', NULL, 3, 0);
    """)
    monkeypatch.setattr("analytics.market_stats.get_connectivity", lambda: connection)

    listings = get_listings_near_location(45.0, 18.0, 2)

    assert [item["id"] for item in listings] == [1]
    assert listings[0]["distance_km"] == 0

    listings = get_listings_near_location(45.0, 18.0, 5)

    assert [item["id"] for item in listings] == [1, 2]
    assert listings[1]["distance_km"] > listings[0]["distance_km"]


def test_existing_users_table_migrates_and_saves_location(tmp_path, monkeypatch):
    from analytics.user_settings import save_user_location
    from database.database import get_connectivity, init_db

    db_path = tmp_path / "location-search.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE users (telegram_id INTEGER PRIMARY KEY, first_name TEXT)"
        )

    init_db(str(Path(__file__).parent / "database" / "schema.sql"), str(db_path))
    init_db(str(Path(__file__).parent / "database" / "schema.sql"), str(db_path))
    monkeypatch.setattr(
        "analytics.user_settings.get_connectivity",
        lambda: get_connectivity(str(db_path)),
    )

    assert save_user_location(123, "Test", 45.55, 18.69)

    connection = get_connectivity(str(db_path))
    try:
        row = connection.execute(
            "SELECT last_latitude, last_longitude FROM users WHERE telegram_id = ?",
            (123,),
        ).fetchone()
        assert tuple(row) == (45.55, 18.69)
        assert connection.execute("SELECT COUNT(*) FROM pois").fetchone()[0] > 0
        assert connection.execute(
            "SELECT COUNT(*) FROM user_saved_listings"
        ).fetchone()[0] == 0
    finally:
        connection.close()