import pytest
from bs4 import BeautifulSoup
from unittest.mock import Mock, patch
from scrapers.health_check import is_listing_text_inactive, check_listing_url_status
from scrapers.njuskalo import parse_njuskalo_card
from scrapers.index_hr import parse_api_item
from database.database import save_or_update_listing, init_db, get_connectivity
from pathlib import Path


def test_is_listing_text_inactive_active_titles():
    assert is_listing_text_inactive("Iznajmljuje se stan u Retfali, 50m2") is False
    assert is_listing_text_inactive("Stan Osijek, centar, novogradnja") is False
    assert is_listing_text_inactive("Iznajmljujem jednosoban stan") is False
    assert is_listing_text_inactive("Najam stana, povoljno") is False
    assert is_listing_text_inactive("") is False
    assert is_listing_text_inactive(None) is False


def test_is_listing_text_inactive_sold_and_expired_phrases():
    assert is_listing_text_inactive("[PRODANO] Dvosobni stan u Osijeku") is True
    assert is_listing_text_inactive("Stan Osijek (PRODAN)") is True
    assert is_listing_text_inactive("IZNAJMLJENO Stan Centar 50m2") is True
    assert is_listing_text_inactive("Stan je iznajmljen studentima") is True
    assert is_listing_text_inactive("Dvosoban stan - REZERVIRANO") is True
    assert is_listing_text_inactive("Stan Retfala [KAPARENO]") is True
    assert is_listing_text_inactive("Oglas je neaktivan") is True
    assert is_listing_text_inactive("Ovaj oglas je neaktivan") is True
    assert is_listing_text_inactive("Ovaj oglas je prodan.") is True
    assert is_listing_text_inactive("Ovaj oglas više nije dostupan.") is True
    assert is_listing_text_inactive("Korisnik je deaktivirao oglas") is True
    assert is_listing_text_inactive("Oglas više nije aktivan") is True


def test_parse_njuskalo_card_skips_inactive_and_non_rentals():
    html_active = """
    <article class="container">
        <h3 class="entity-title"><a href="/nekretnine/stan-osijek-50m2-oglas-1001">Lijep stan 50m2</a></h3>
        <strong class="price">400 &euro;</strong>
        <div class="entity-description">Namješten stan u Retfali</div>
    </article>
    """
    card_active = BeautifulSoup(html_active, "html.parser")
    parsed_active = parse_njuskalo_card(card_active)
    assert parsed_active is not None
    assert parsed_active["price"] == 400.0
    assert parsed_active["external_id"] == "1001"

    html_car = """
    <article class="container">
        <h3 class="entity-title"><a href="/auti/bmw-320d-oglas-1002">BMW 320d</a></h3>
        <strong class="price">5000 &euro;</strong>
    </article>
    """
    assert parse_njuskalo_card(BeautifulSoup(html_car, "html.parser")) is None

    html_sold = """
    <article class="container">
        <h3 class="entity-title"><a href="/nekretnine/stan-oglas-1003">[PRODANO] Stan Osijek</a></h3>
        <strong class="price">350 &euro;</strong>
    </article>
    """
    assert parse_njuskalo_card(BeautifulSoup(html_sold, "html.parser")) is None

    html_unavailable = """
    <article class="container ClassifiedDetailUnavailableNotice">
        <h3 class="entity-title"><a href="/nekretnine/stan-oglas-1004">Stan Osijek</a></h3>
        <strong class="price">350 &euro;</strong>
    </article>
    """
    assert parse_njuskalo_card(BeautifulSoup(html_unavailable, "html.parser")) is None


def test_parse_api_item_index_skips_inactive_and_sold():
    valid_active = {
        "id": "abc-1",
        "code": 7500001,
        "smartLink": "stan-osijek-50m2",
        "title": "Stan Osijek 50m2 najam",
        "price": "450",
        "status": 1,
        "category": "najam-stanova",
        "module": "nekretnine",
    }
    parsed = parse_api_item(valid_active)
    assert parsed is not None
    assert parsed["external_id"] == "7500001"

    item_sold = {**valid_active, "status": 3}
    assert parse_api_item(item_sold) is None

    item_paused = {**valid_active, "status": 2}
    assert parse_api_item(item_paused) is None

    item_sold_title = {**valid_active, "status": 1, "title": "Stan Osijek [IZNAJMLJENO]"}
    assert parse_api_item(item_sold_title) is None


def test_check_listing_url_status_index_api(monkeypatch):
    mock_head = Mock(status_code=200, url="https://www.index.hr/oglasi/nekretnine/najam-stanova/oglas/stan/7542853")
    monkeypatch.setattr("scrapers.health_check.requests.head", lambda *a, **kw: mock_head)

    def mock_get(url, *a, **kw):
        if "single-ad" in url:
            mock_resp = Mock(status_code=200)
            mock_resp.json.return_value = {"count": 1, "data": [{"status": 3, "title": "Stan"}]}
            return mock_resp
        return Mock(status_code=200, url=url, text="<html>Active</html>")

    monkeypatch.setattr("scrapers.health_check.requests.get", mock_get)
    assert check_listing_url_status("https://www.index.hr/oglasi/nekretnine/najam-stanova/oglas/stan/7542853", "Index Oglasnik") is False


def test_check_listing_url_status_njuskalo_notice(monkeypatch):
    mock_head = Mock(status_code=200, url="https://www.njuskalo.hr/nekretnine/stan-oglas-5000")
    monkeypatch.setattr("scrapers.health_check.requests.head", lambda *a, **kw: mock_head)

    html_notice = """
    <html>
        <body>
            <div class="ClassifiedDetailUnavailableNotice">
                <h3 class="ClassifiedDetailUnavailableNotice-title">Ovaj oglas je prodan.</h3>
            </div>
        </body>
    </html>
    """
    mock_get = Mock(status_code=200, url="https://www.njuskalo.hr/nekretnine/stan-oglas-5000", text=html_notice)
    monkeypatch.setattr("scrapers.health_check.requests.get", lambda *a, **kw: mock_get)

    assert check_listing_url_status("https://www.njuskalo.hr/nekretnine/stan-oglas-5000", "Nju\u0161kalo") is False


def test_save_or_update_listing_explicit_is_active(tmp_path):
    db_path = tmp_path / "test_inactive.sqlite"
    schema_path = Path(__file__).parent.parent / "database" / "schema.sql"
    init_db(str(schema_path), str(db_path))

    listing = {
        "external_id": "test-inact-1",
        "source_platform": "Test",
        "title": "Stan za najam",
        "price": 300,
        "url": "https://example.com/inact-1",
        "is_active": 0,
    }
    status, lid = save_or_update_listing(listing, str(db_path))
    assert status == "inserted"

    with get_connectivity(str(db_path)) as conn:
        row = conn.execute("SELECT is_active FROM listings WHERE id = ?", (lid,)).fetchone()
        assert row["is_active"] == 0
