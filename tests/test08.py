import sqlite3
import pytest
from analytics.feature_extractor import extract_features, format_feature_badges
from analytics.market_stats import get_map_listings_and_pois


def test_utilities_extraction_included():
    text = "Prekrasan stan, cijena 400 EUR. Sve režije uključene u cijenu najma!"
    features = extract_features(description=text)
    assert features["utilities_included"] is True
    assert features["utilities_separate"] is False


def test_utilities_extraction_separate_and_estimate():
    text = "Najam garsonijere 320 €. Režije se plaćaju posebno, ljeti cca 60 €, zimi cca 90 €."
    features = extract_features(description=text)
    assert features["utilities_included"] is False
    assert features["utilities_separate"] is True
    assert features["utilities_est"] is not None
    assert "60" in features["utilities_est"] or "90" in features["utilities_est"]


def test_deposit_extraction_variations():
    # 1 month rent deposit
    f1 = extract_features(description="Obavezan polog u visini jedne mjesečne najamnine.")
    assert f1["deposit"] == "1 mjesečna najamnina"

    # Specific amount deposit
    f2 = extract_features(description="Iznajmljuje se stan, polog 400 €.")
    assert f2["deposit"] == "400 €"

    # No deposit
    f3 = extract_features(description="Stan za studente, bez pologa!")
    assert f3["deposit"] == "Bez pologa"


def test_conditions_extraction():
    text = "Ugovor o najmu obavezan, prijava na MUP. Isključivo nepušači, bez kućnih ljubimaca."
    features = extract_features(description=text)
    assert features["non_smokers"] is True
    assert features["contract_required"] is True
    assert features["pet_prohibited"] is True


def test_format_feature_badges_includes_financials():
    title = "Stan Retfala"
    description = "Cijena s režijama, polog 300 €, ima parking i lift."
    badges = format_feature_badges(title, description)
    assert "Režije" in badges
    assert "Polog" in badges
    assert "Parking" in badges
    assert "Lift" in badges


def test_get_map_listings_and_pois(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE locations (id INTEGER PRIMARY KEY, name TEXT, latitude REAL, longitude REAL);
        CREATE TABLE listings (
            id INTEGER PRIMARY KEY, title TEXT, description TEXT, price REAL, area_sqm REAL,
            source_platform TEXT, url TEXT, image_url TEXT, location_id INTEGER, is_active INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE pois (
            id INTEGER PRIMARY KEY, key_name TEXT, name TEXT, category TEXT, latitude REAL, longitude REAL
        );

        INSERT INTO locations VALUES (1, 'Centar', 45.555, 18.695);
        INSERT INTO listings VALUES (1, 'Stan Centar', 'Režije u cijeni', 400, 50, 'Njuškalo', 'https://test.com', NULL, 1, 1, CURRENT_TIMESTAMP);
        INSERT INTO pois VALUES (1, 'kampus', 'Sveučilišni kampus', 'education', 45.554, 18.703);
    """)

    monkeypatch.setattr("analytics.market_stats.get_connectivity", lambda: conn)
    monkeypatch.setattr("analytics.poi.get_connectivity", lambda: conn)

    data = get_map_listings_and_pois()
    assert "listings" in data
    assert "pois" in data
    assert len(data["listings"]) == 1
    assert data["listings"][0]["utilities_included"] is True
    assert len(data["pois"]) == 1

