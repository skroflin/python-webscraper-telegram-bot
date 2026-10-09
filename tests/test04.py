import sqlite3
from pathlib import Path

from analytics.match_scorer import calculate_match_score
from analytics.market_stats import (
    get_latest_listings,
    get_listings_near_location,
    get_market_analytics,
)
from analytics.user_settings import get_all_users_with_preferences, reset_user_filters
from database.database import get_connectivity, init_db, save_or_update_listing
from scrapers.health_check import check_listing_url_status, run_health_check


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

    init_db(str(Path(__file__).parent.parent / "database" / "schema.sql"), str(db_path))
    init_db(str(Path(__file__).parent.parent / "database" / "schema.sql"), str(db_path))
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


def test_reset_user_filters_clears_neighborhoods_and_priorities(monkeypatch):
    from analytics.user_settings import get_connectivity

    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE users (
            telegram_id INTEGER PRIMARY KEY, max_price REAL, min_area REAL,
            must_have_lift INTEGER, must_have_pet INTEGER, must_have_parking INTEGER,
            location_focus TEXT
        );
        CREATE TABLE user_locations (user_id INTEGER, location_id INTEGER);
        INSERT INTO users VALUES (7, 500, 40, 1, 1, 1, 'center');
        INSERT INTO user_locations VALUES (7, 2);
    """)
    monkeypatch.setattr("analytics.user_settings.get_connectivity", lambda: connection)

    assert reset_user_filters(7)

    user = connection.execute("SELECT * FROM users WHERE telegram_id = 7").fetchone()
    assert user["max_price"] is None
    assert user["min_area"] is None
    assert user["must_have_lift"] == 0
    assert user["location_focus"] == "none"
    assert connection.execute("SELECT COUNT(*) FROM user_locations").fetchone()[0] == 0


def test_missing_area_does_not_earn_minimum_area_points():
    score, reasons = calculate_match_score(
        {"price": 300, "area_sqm": None},
        {"max_price": 500, "min_area": 40},
    )

    assert score == 20
    assert any("Kvadratura nije navedena" in reason for reason in reasons)


def test_market_stats_and_latest_listings_exclude_inactive(monkeypatch):
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE listings (
            id INTEGER PRIMARY KEY, title TEXT, price REAL, area_sqm REAL,
            source_platform TEXT, url TEXT, is_active INTEGER, created_at TEXT
        );
        INSERT INTO listings VALUES (1, 'Aktivan', 300, 50, 'Test', 'https://example.com/1', 1, '2025-01-01');
        INSERT INTO listings VALUES (2, 'Neaktivan', 100, 20, 'Test', 'https://example.com/2', 0, '2026-01-01');
    """)
    monkeypatch.setattr("analytics.market_stats.get_connectivity", lambda: connection)

    stats = get_market_analytics()
    latest = get_latest_listings()

    assert stats["total"] == 1
    assert stats["avg_price"] == 300
    assert [item["title"] for item in latest] == ["Aktivan"]


def test_all_users_and_neighborhoods_are_loaded_with_one_query(monkeypatch):
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE users (telegram_id INTEGER PRIMARY KEY, first_name TEXT, max_price REAL, min_area REAL);
        CREATE TABLE user_locations (user_id INTEGER, location_id INTEGER);
        INSERT INTO users VALUES (1, 'Ana', 500, 40);
        INSERT INTO users VALUES (2, 'Ivo', NULL, NULL);
        INSERT INTO user_locations VALUES (1, 3);
    """)
    statements = []
    connection.set_trace_callback(statements.append)
    monkeypatch.setattr("analytics.user_settings.get_connectivity", lambda: connection)

    users = get_all_users_with_preferences()

    assert users[0]["location_ids"] == [3]
    assert users[1]["location_ids"] == []
    assert sum(statement.lstrip().upper().startswith("SELECT") for statement in statements) == 1


def test_health_check_treats_404_as_inactive_and_403_as_unknown(monkeypatch):
    from unittest.mock import Mock

    with monkeypatch.context() as patch_context:
        patch_context.setattr(
            "scrapers.health_check.requests.head",
            lambda *args, **kwargs: Mock(status_code=404, url=args[0]),
        )
        assert check_listing_url_status("https://example.com/gone", "Index") is False

    with monkeypatch.context() as patch_context:
        patch_context.setattr(
            "scrapers.health_check.requests.head",
            lambda *args, **kwargs: Mock(status_code=403, url=args[0]),
        )
        patch_context.setattr(
            "scrapers.health_check.requests.get",
            lambda *args, **kwargs: Mock(status_code=403, url=args[0]),
        )
        assert check_listing_url_status("https://example.com/blocked", "Index") is None


def test_health_check_deactivates_only_confirmed_removals(monkeypatch):
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE listings (
            id INTEGER PRIMARY KEY, title TEXT, url TEXT, source_platform TEXT,
            is_active INTEGER, updated_at TEXT
        );
        INSERT INTO listings VALUES (1, 'Gone', 'https://example.com/gone', 'Index', 1, NULL);
        INSERT INTO listings VALUES (2, 'Blocked', 'https://example.com/blocked', 'Index', 1, NULL);
        INSERT INTO listings VALUES (3, 'Live', 'https://example.com/live', 'Index', 1, NULL);
    """)
    monkeypatch.setattr("scrapers.health_check.get_connectivity", lambda db_path=None: connection)
    monkeypatch.setattr(
        "scrapers.health_check.check_listing_url_status",
        lambda url, source: {
            "https://example.com/gone": False,
            "https://example.com/blocked": None,
            "https://example.com/live": True,
        }[url],
    )

    assert run_health_check(max_workers=2) == (3, 1)
    statuses = connection.execute(
        "SELECT id, is_active FROM listings ORDER BY id"
    ).fetchall()
    assert [(row["id"], row["is_active"]) for row in statuses] == [(1, 0), (2, 1), (3, 1)]


def test_existing_listing_refreshes_metadata_and_reactivates(tmp_path):
    db_path = tmp_path / "listing-refresh.sqlite"
    schema_path = Path(__file__).parent.parent / "database" / "schema.sql"
    init_db(str(schema_path), str(db_path))
    listing = {
        "external_id": "abc-1",
        "source_platform": "Test",
        "title": "Stan za najam",
        "description": "Prvi opis",
        "price": 400,
        "area_sqm": 45,
        "location_id": 2,
        "raw_address": "Retfala",
        "url": "https://example.com/listing/1",
        "image_url": "https://example.com/old.jpg",
    }

    status, listing_id = save_or_update_listing(listing, str(db_path))
    assert status == "inserted"
    connection = get_connectivity(str(db_path))
    try:
        connection.execute("UPDATE listings SET is_active = 0 WHERE id = ?", (listing_id,))
        connection.commit()
    finally:
        connection.close()

    updated = {
        **listing,
        "title": "Stan za najam, renoviran",
        "description": "Ažurirani opis",
        "price": 350,
        "area_sqm": 50,
        "image_url": "https://example.com/new.jpg",
    }
    status, updated_id = save_or_update_listing(updated, str(db_path))

    assert status == "price_drop"
    assert updated_id == listing_id
    connection = get_connectivity(str(db_path))
    try:
        row = connection.execute(
            "SELECT title, description, price, area_sqm, image_url, is_active "
            "FROM listings WHERE id = ?",
            (listing_id,),
        ).fetchone()
        assert tuple(row) == (
            "Stan za najam, renoviran", "Ažurirani opis", 350, 50,
            "https://example.com/new.jpg", 1,
        )
        assert connection.execute(
            "SELECT old_price, new_price FROM price_history WHERE listing_id = ?",
            (listing_id,),
        ).fetchone()[:] == (400, 350)
    finally:
        connection.close()