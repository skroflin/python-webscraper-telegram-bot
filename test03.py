import json
import pytest
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup

from scrapers.index_hr import (
    parse_price,
    parse_area,
    match_location_id,
    extract_from_next_data,
    extract_from_html,
    scrape_index_osijek,
    run_index_scraper_and_save,
)


class TestHelperFunctions:

    @pytest.mark.parametrize("input_val, expected", [
        ("450 EUR", 450.00),
        ("1.200,50 EUR", 1200.50),
        (500, 500.0),
        (350.5, 350.5),
        (None, 0.0),
        ("", 0.0),
        ("Cijena na upit", 0.0)
    ])
    def test_parse_price(self, input_val, expected):
        assert parse_price(input_val) == expected

    @pytest.mark.parametrize("input_text, expected", [
        ("Stan u Osijeku, 55 m2", 55.0),
        ("Iznajmljuje se stan 45 m2", 45.0),
        ("Stan 60 kvadrata", 60.0),
        ("Bez kvadrature u opisu", None),
        (None, None)
    ])
    def test_parse_area(self, input_text, expected):
        assert parse_area(input_text) == expected

    @patch("scrapers.index_hr.get_connectivity")
    def test_match_location_id_from_db(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [{"id": 2, "name": "Retfala"}]
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__.return_value = mock_conn
        mock_get_conn.return_value = mock_conn

        assert match_location_id("Stan Retfala, trosoban") == 2

    @patch("scrapers.index_hr.get_connectivity", side_effect=Exception("Db error"))
    def test_match_location_id_fallback_map(self, mock_get_conn):
        assert match_location_id("Stan u GGO-u") == 6
        assert match_location_id("Stan u DGO-u") == 5
        assert match_location_id("Nepoznat kvart") is None


class TestExtractors:

    def test_extract_from_next_data_success(self):
        next_data_payload = {
            "props": {
                "pageProps": {
                    "searchResults": {
                        "ads": [
                            {
                                "id": "12345",
                                "url": "/oglas/12345",
                                "title": "Stan RTF 50 m2",
                                "price": "400 EUR",
                                "description": "Stan u Retfali",
                                "surfaceArea": "50"
                            }
                        ]
                    }
                }
            }
        }
        html_content = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(next_data_payload)}</script></html>'
        soup = BeautifulSoup(html_content, "html.parser")

        with patch("scrapers.index_hr.match_location_id", return_value=2):
            results = extract_from_next_data(soup)

        assert len(results) == 1
        assert results[0]["external_id"] == "12345"
        assert results[0]["title"] == "Stan RTF 50 m2"
        assert results[0]["price"] == 400.0
        assert results[0]["location_id"] == 2


class TestScraperFlow:

    @patch("scrapers.index_hr.requests.get")
    @patch("scrapers.index_hr.extract_from_next_data")
    @patch("scrapers.index_hr.time.sleep")
    def test_scrape_index_osijek_pagination(self, mock_sleep, mock_extract, mock_requests):
        mock_response = MagicMock()
        mock_response.content = b"<html></html>"
        mock_response.raise_for_status.return_value = None
        mock_requests.return_value = mock_response

        mock_extract.side_effect = [
            [{"url": "https://www.index.hr/oglas/1"}],
            [{"url": "https://www.index.hr/oglas/2"}]
        ]

        results = scrape_index_osijek(max_pages=2)

        assert len(results) == 2
        assert mock_requests.call_count == 2
        assert mock_sleep.call_count == 1

    @patch("scrapers.index_hr.scrape_index_osijek")
    @patch("scrapers.index_hr.save_or_update_listing")
    def test_run_index_scraper_and_save_status(self, mock_save, mock_scrape):
        mock_scrape.return_value = [
            {"url": "https://www.index.hr/oglas/1"},
            {"url": "https://www.index.hr/oglas/2"},
            {"url": "https://www.index.hr/oglas/3"},
            {"url": "https://www.index.hr/oglas/4"}
        ]

        mock_save.side_effect = [
            ("inserted", 1),
            ("exists", 2),
            ("price_updated", 3),
            ("duplicate_cross_post", 4)
        ]

        stats = run_index_scraper_and_save(max_pages=1)

        assert stats["inserted"] == 1
        assert stats["exists"] == 1
        assert stats["price_updated"] == 1
        assert stats["duplicates"] == 1