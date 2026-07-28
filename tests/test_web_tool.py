"""Tests for the web_tool module."""

from unittest.mock import patch, MagicMock

import pytest
from web_tool import search_web, get_news


class TestSearchWeb:
    """Tests for search_web."""

    @patch("web_tool.DDGS")
    def test_search_returns_results(self, mock_ddgs_class):
        """Search should format results correctly."""
        mock_ddgs = MagicMock()
        mock_ddgs.text.return_value = [
            {"title": "Result 1", "body": "Description 1"},
            {"title": "Result 2", "body": "Description 2"},
        ]
        mock_ddgs_class.return_value.__enter__.return_value = mock_ddgs

        result = search_web("python testing")
        assert "Result 1" in result
        assert "Description 1" in result
        assert "Result 2" in result
        assert "[1]" in result

    @patch("web_tool.DDGS")
    def test_no_results(self, mock_ddgs_class):
        """Search with no results returns a message."""
        mock_ddgs = MagicMock()
        mock_ddgs.text.return_value = []
        mock_ddgs_class.return_value.__enter__.return_value = mock_ddgs

        result = search_web("asdfghjklqwertyuiop")
        assert "No results found" in result

    @patch("web_tool.DDGS")
    def test_search_error(self, mock_ddgs_class):
        """Search error should be caught."""
        mock_ddgs = MagicMock()
        mock_ddgs.text.side_effect = Exception("API error")
        mock_ddgs_class.return_value.__enter__.return_value = mock_ddgs

        result = search_web("test")
        assert "Error" in result


class TestGetNews:
    """Tests for get_news."""

    @patch("web_tool.requests.get")
    def test_news_returns_formatted_results(self, mock_get):
        """News should format RSS results correctly."""
        mock_response = MagicMock()
        mock_response.text = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Test News 1</title>
      <pubDate>Mon, 28 Jul 2026 12:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Test News 2</title>
      <pubDate>Mon, 28 Jul 2026 11:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = get_news("space")
        assert "Test News 1" in result
        assert "Test News 2" in result
        assert "2026" in result

    @patch("web_tool.requests.get")
    def test_news_empty_channel(self, mock_get):
        """Empty channel should return a message."""
        mock_response = MagicMock()
        mock_response.text = """<?xml version="1.0"?>
<rss version="2.0">
  <channel></channel>
</rss>"""
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = get_news("test")
        assert "No news" in result or "No news" in result

    @patch("web_tool.requests.get")
    def test_news_http_error(self, mock_get):
        """HTTP error should be caught."""
        mock_get.side_effect = Exception("HTTP 500")

        result = get_news("test")
        assert "Error" in result
