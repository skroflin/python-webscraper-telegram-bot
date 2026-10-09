import sqlite3
import pytest
from unittest.mock import AsyncMock, MagicMock

from analytics.feature_extractor import extract_features
from analytics.match_scorer import calculate_match_score
from analytics.user_settings import (
    get_user_profile,
    get_user_priorities,
    toggle_user_priority,
    get_all_users_with_preferences,
)
from bot.notifier import notify_users_about_listing


def test_feature_extractor_detects_prohibitions():
    # Pets prohibited
    features = extract_features("Stan u Retfali", "Iznajmljuje se stan, bez kućnih ljubimaca.")
    assert features["pet_friendly"] is False
    assert features["pet_prohibited"] is True

    # Pet friendly
    features_ok = extract_features("Stan u Centru", "Pet friendly stan, dozvoljeni manji ljubimci.")
    assert features_ok["pet_friendly"] is True
    assert features_ok["pet_prohibited"] is False

    # Elevator negative
    features_no_lift = extract_features("Stan 4. kat", "Zgrada nema lift.")
    assert features_no_lift["elevator"] is False
    assert features_no_lift["elevator_negative"] is True

    # Elevator positive
    features_lift = extract_features("Stan 4. kat", "Zgrada ima lift.")
    assert features_lift["elevator"] is True
    assert features_lift["elevator_negative"] is False


def test_toggle_user_priority_switches_flags(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE users (
            telegram_id INTEGER PRIMARY KEY,
            first_name TEXT,
            max_price REAL,
            min_area REAL,
            must_have_lift INTEGER DEFAULT 0,
            must_have_pet INTEGER DEFAULT 0,
            must_have_parking INTEGER DEFAULT 0,
            location_focus TEXT DEFAULT 'none'
        );
    """)
    monkeypatch.setattr("analytics.user_settings.get_connectivity", lambda: conn)

    # First toggle for new user: 0 -> 1
    new_val = toggle_user_priority(101, "must_have_lift", "Marko")
    assert new_val == 1

    profile = get_user_profile(101)
    assert profile["must_have_lift"] == 1
    assert profile["must_have_pet"] == 0

    # Second toggle: 1 -> 0
    new_val = toggle_user_priority(101, "must_have_lift", "Marko")
    assert new_val == 0
    profile = get_user_profile(101)
    assert profile["must_have_lift"] == 0

    # Toggle pet and parking
    assert toggle_user_priority(101, "must_have_pet", "Marko") == 1
    assert toggle_user_priority(101, "must_have_parking", "Marko") == 1

    priorities = get_user_priorities(101)
    assert priorities["must_have_pet"] == 1
    assert priorities["must_have_parking"] == 1


def test_match_scorer_prioritizes_user_preferences():
    listing_pet_ok = {
        "title": "Stan Retfala",
        "description": "Pet friendly, ima parking i lift.",
        "price": 400,
        "area_sqm": 50,
    }
    listing_pet_forbidden = {
        "title": "Stan Retfala",
        "description": "Bez kućnih ljubimaca, nema lift.",
        "price": 400,
        "area_sqm": 50,
    }

    # User requiring pet friendly
    score_ok, reasons_ok = calculate_match_score(
        listing_pet_ok,
        user_profile={"must_have_pet": 1, "must_have_lift": 1, "must_have_parking": 1},
    )
    assert any("Pet friendly (traženo)" in r for r in reasons_ok)
    assert any("Zgrada ima lift (traženo)" in r for r in reasons_ok)
    assert any("Parking / Garaža (traženo)" in r for r in reasons_ok)

    score_bad, reasons_bad = calculate_match_score(
        listing_pet_forbidden,
        user_profile={"must_have_pet": 1, "must_have_lift": 1},
    )
    assert any("Kućni ljubimci NISU dozvoljeni" in r for r in reasons_bad)
    assert any("Zgrada NEMA lift" in r for r in reasons_bad)
    assert score_bad < score_ok


@pytest.mark.anyio
async def test_notifier_respects_must_have_vetoes(monkeypatch):
    users = [
        {
            "telegram_id": 1,
            "first_name": "PetOwner",
            "max_price": 500,
            "min_area": 40,
            "must_have_pet": 1,
            "must_have_lift": 0,
            "must_have_parking": 0,
            "location_ids": [],
        },
        {
            "telegram_id": 2,
            "first_name": "NormalUser",
            "max_price": 500,
            "min_area": 40,
            "must_have_pet": 0,
            "must_have_lift": 0,
            "must_have_parking": 0,
            "location_ids": [],
        },
    ]

    monkeypatch.setattr("bot.notifier.get_all_users_with_preferences", lambda: users)
    monkeypatch.setattr("bot.notifier.get_all_pois_from_db", lambda: [])

    app_mock = MagicMock()
    app_mock.bot.send_message = AsyncMock()

    # Listing that strictly rejects pets
    listing = {
        "id": 1,
        "title": "Stan Osijek",
        "description": "Zabranjeno za ljubimce, samo ozbiljni najmoprimci.",
        "price": 350,
        "area_sqm": 45,
        "url": "https://example.com/ad/1",
    }

    await notify_users_about_listing(app_mock, listing, event_type="inserted", min_score_threshold=10)

    # PetOwner should NOT be notified, only NormalUser
    called_chat_ids = [call.kwargs["chat_id"] for call in app_mock.bot.send_message.call_args_list]
    assert 1 not in called_chat_ids
    assert 2 in called_chat_ids
