"""Tests for scripts.sitemaps.status_check."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from scripts.sitemaps.status_check import (
    _check_url,
    _parse_sitemap_urls,
    _resolve_sitemap_url,
    status_check,
)

SAMPLE_SITEMAP = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/page1</loc></url>
  <url><loc>https://example.com/page2</loc></url>
  <url><loc>https://example.com/page3</loc></url>
</urlset>
"""

SITEMAP_INDEX = """\
<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap-posts.xml</loc></sitemap>
</sitemapindex>
"""

EMPTY_SITEMAP = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
</urlset>
"""


class TestResolveSitemapUrl:
    def test_xml_url_returned_as_is(self):
        assert _resolve_sitemap_url("https://example.com/sitemap.xml") == "https://example.com/sitemap.xml"

    def test_bare_domain_gets_sitemap_appended(self):
        assert _resolve_sitemap_url("https://example.com") == "https://example.com/sitemap.xml"

    def test_bare_domain_with_path_gets_stripped(self):
        assert _resolve_sitemap_url("https://example.com/blog") == "https://example.com/sitemap.xml"

    def test_no_scheme_defaults_to_https(self):
        result = _resolve_sitemap_url("example.com")
        assert result.startswith("https://")
        assert result.endswith("/sitemap.xml")

    def test_case_insensitive_xml_check(self):
        assert _resolve_sitemap_url("https://example.com/sitemap.XML") == "https://example.com/sitemap.XML"


class TestParseSitemapUrls:
    def test_extracts_urls_from_valid_sitemap(self):
        urls = _parse_sitemap_urls(SAMPLE_SITEMAP)
        assert urls == [
            "https://example.com/page1",
            "https://example.com/page2",
            "https://example.com/page3",
        ]

    def test_raises_on_sitemap_index(self):
        with pytest.raises(ValueError, match="sitemap index"):
            _parse_sitemap_urls(SITEMAP_INDEX)

    def test_raises_on_empty_sitemap(self):
        with pytest.raises(ValueError, match="No <url><loc> entries"):
            _parse_sitemap_urls(EMPTY_SITEMAP)


class TestCheckUrl:
    def test_successful_request(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "text/html", "Content-Length": "1234"}

        with patch("scripts.sitemaps.status_check.requests.get", return_value=mock_resp):
            row = _check_url("https://example.com/page1", timeout=10.0, user_agent="TestBot")

        assert row["url"] == "https://example.com/page1"
        assert row["status_code"] == "200"
        assert row["content_type"] == "text/html"
        assert row["content_length"] == "1234"
        assert int(row["response_time_ms"]) >= 0
        assert row["error"] == ""

    def test_connection_error_recorded(self):
        with patch(
            "scripts.sitemaps.status_check.requests.get",
            side_effect=requests.ConnectionError("refused"),
        ):
            row = _check_url("https://example.com/down", timeout=10.0, user_agent="TestBot")

        assert row["status_code"] == ""
        assert row["response_time_ms"] == ""
        assert "refused" in row["error"]

    def test_timeout_error_recorded(self):
        with patch(
            "scripts.sitemaps.status_check.requests.get",
            side_effect=requests.Timeout("timed out"),
        ):
            row = _check_url("https://example.com/slow", timeout=1.0, user_agent="TestBot")

        assert row["status_code"] == ""
        assert "timed out" in row["error"]

    def test_passes_user_agent_header(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {}

        with patch("scripts.sitemaps.status_check.requests.get", return_value=mock_resp) as mock_get:
            _check_url("https://example.com", timeout=5.0, user_agent="CustomBot/1.0")

        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["headers"]["User-Agent"] == "CustomBot/1.0"


class TestStatusCheck:
    def _mock_sitemap_response(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.text = SAMPLE_SITEMAP
        resp.raise_for_status = MagicMock()
        return resp

    def _mock_page_response(self, status_code=200):
        resp = MagicMock()
        resp.status_code = status_code
        resp.headers = {"Content-Type": "text/html; charset=utf-8", "Content-Length": "5678"}
        return resp

    def test_produces_csv_with_correct_columns(self, tmp_path):
        sitemap_resp = self._mock_sitemap_response()
        page_resp = self._mock_page_response()

        with (
            patch(
                "scripts.sitemaps.status_check.requests.get",
                side_effect=[sitemap_resp, page_resp, page_resp, page_resp],
            ),
            patch("scripts.sitemaps.status_check.time.sleep"),
        ):
            result = status_check("https://example.com/sitemap.xml", tmp_path, delay=0.0)

        assert result.exists()
        assert result.suffix == ".csv"
        lines = result.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 4
        header = lines[0]
        assert "url" in header
        assert "status_code" in header
        assert "response_time_ms" in header
        assert "content_type" in header
        assert "content_length" in header

    def test_output_filename_contains_domain(self, tmp_path):
        sitemap_resp = self._mock_sitemap_response()
        page_resp = self._mock_page_response()

        with (
            patch(
                "scripts.sitemaps.status_check.requests.get",
                side_effect=[sitemap_resp, page_resp, page_resp, page_resp],
            ),
            patch("scripts.sitemaps.status_check.time.sleep"),
        ):
            result = status_check("https://example.com/sitemap.xml", tmp_path, delay=0.0)

        assert "example.com" in result.name

    def test_delay_jitter_applied_between_requests(self, tmp_path):
        sitemap_resp = self._mock_sitemap_response()
        page_resp = self._mock_page_response()

        with (
            patch(
                "scripts.sitemaps.status_check.requests.get",
                side_effect=[sitemap_resp, page_resp, page_resp, page_resp],
            ),
            patch("scripts.sitemaps.status_check.time.sleep") as mock_sleep,
        ):
            status_check("https://example.com/sitemap.xml", tmp_path, delay=1.0)

        assert mock_sleep.call_count == 2
        for call in mock_sleep.call_args_list:
            delay_val = call[0][0]
            assert 0.8 <= delay_val <= 1.2

    def test_resolves_bare_domain_to_sitemap_url(self, tmp_path):
        sitemap_resp = self._mock_sitemap_response()
        page_resp = self._mock_page_response()

        with (
            patch(
                "scripts.sitemaps.status_check.requests.get",
                side_effect=[sitemap_resp, page_resp, page_resp, page_resp],
            ) as mock_get,
            patch("scripts.sitemaps.status_check.time.sleep"),
        ):
            status_check("https://example.com", tmp_path, delay=0.0)

        first_call_url = mock_get.call_args_list[0][0][0]
        assert first_call_url == "https://example.com/sitemap.xml"

    def test_sitemap_fetch_failure_raises(self, tmp_path):
        with patch(
            "scripts.sitemaps.status_check.requests.get",
            side_effect=requests.ConnectionError("unreachable"),
        ):
            with pytest.raises(requests.ConnectionError):
                status_check("https://example.com/sitemap.xml", tmp_path)

    def test_no_delay_after_last_url(self, tmp_path):
        single_sitemap = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/only</loc></url>
</urlset>
"""
        sitemap_resp = MagicMock()
        sitemap_resp.status_code = 200
        sitemap_resp.text = single_sitemap
        sitemap_resp.raise_for_status = MagicMock()
        page_resp = self._mock_page_response()

        with (
            patch("scripts.sitemaps.status_check.requests.get", side_effect=[sitemap_resp, page_resp]),
            patch("scripts.sitemaps.status_check.time.sleep") as mock_sleep,
        ):
            status_check("https://example.com/sitemap.xml", tmp_path, delay=1.0)

        mock_sleep.assert_not_called()
