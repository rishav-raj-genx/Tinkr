import urllib.parse
import xml.etree.ElementTree as ET

import requests
from duckduckgo_search import DDGS

from logger import get_logger

logger = get_logger("web_tool")


def search_web(query: str) -> str:
    """Searches the web using DuckDuckGo and returns a summary of the results."""
    logger.info("Searching web for: %s", query)
    try:
        with DDGS(timeout=10.0) as ddgs:
            results = list(ddgs.text(query, max_results=3))
            if not results:
                return "No results found."

            output = ""
            for i, result in enumerate(results):
                output += f"[{i+1}] Title: {result.get('title')}\nSnippet: {result.get('body')}\n\n"
            return output
    except Exception as e:
        logger.error("Web search failed: %s", e)
        return f"Error searching the web: {e}"


def get_news(query: str) -> str:
    """Fetches the latest news headlines using Google News RSS."""
    logger.info("Fetching news for: %s", query)
    try:
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-US&gl=US&ceid=US:en"
        response = requests.get(url, timeout=10.0)
        response.raise_for_status()

        root = ET.fromstring(response.text)
        channel = root.find("channel")

        if channel is None:
            return "No news channel found in response."

        items = channel.findall("item")
        if not items:
            return "No news results found."

        output = ""
        for i, item in enumerate(items[:3]):
            title = item.find("title").text if item.find("title") is not None else "No Title"
            date = item.find("pubDate").text if item.find("pubDate") is not None else "No Date"
            output += f"[{i+1}] Title: {title}\nDate: {date}\n\n"

        return output
    except Exception as e:
        logger.error("News search failed: %s", e)
        return f"Error fetching news: {e}"


if __name__ == "__main__":
    logger.info(get_news("latest news about space x"))
