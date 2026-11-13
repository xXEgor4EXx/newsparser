"""Scraper for RSS feeds from major business media, official agencies and regional outlets."""

import email.utils
from datetime import datetime
from typing import List, Dict, Any, Optional
import feedparser
from bs4 import BeautifulSoup
from src.schemas import RawNewsItem, SourceType


DEFAULT_RSS_SOURCES = [
    {
        "name": "РБК Экономика",
        "type": SourceType.MEDIA,
        "url": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss"
    },
    {
        "name": "Коммерсантъ Экономика",
        "type": SourceType.MEDIA,
        "url": "https://www.kommersant.ru/RSS/section-economics.xml"
    },
    {
        "name": "Ведомости Недвижимость",
        "type": SourceType.MEDIA,
        "url": "https://www.vedomosti.ru/rss/rubric/realty.xml"
    },
    {
        "name": "74.RU Челябинск",
        "type": SourceType.MEDIA,
        "url": "https://74.ru/text/rss.xml"
    },
    {
        "name": "Банк России (ЦБ РФ)",
        "type": SourceType.OFFICIAL,
        "url": "https://www.cbr.ru/rss/RssNews"
    }
]


class RSSScraper:
    def __init__(self, sources: Optional[List[Dict[str, Any]]] = None):
        self.sources = sources or DEFAULT_RSS_SOURCES

    def clean_html(self, html_text: str) -> str:
        if not html_text:
            return ""
        soup = BeautifulSoup(html_text, "html.parser")
        return soup.get_text(separator=" ", strip=True)

    def parse_pubdate(self, entry: Any) -> str:
        """Standardizes publication date to ISO datetime or YYYY-MM-DD."""
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                dt = datetime(*entry.published_parsed[:6])
                return dt.strftime("%Y-%m-%dT%H:%M:%S")
            except Exception:
                pass
        if hasattr(entry, "published") and entry.published:
            try:
                parsed_time = email.utils.parsedate_to_datetime(entry.published)
                return parsed_time.strftime("%Y-%m-%dT%H:%M:%S")
            except Exception:
                pass
        return datetime.utcnow().strftime("%Y-%m-%d")

    def fetch_feed(self, source: Dict[str, Any]) -> List[RawNewsItem]:
        items: List[RawNewsItem] = []
        feed = feedparser.parse(source["url"])

        for entry in feed.entries:
            title = entry.get("title", "").strip()
            summary = entry.get("summary", "") or entry.get("description", "")
            clean_text = self.clean_html(summary)
            link = entry.get("link", "").strip()
            pub_date = self.parse_pubdate(entry)

            if not title or not link:
                continue

            item = RawNewsItem(
                source_name=source["name"],
                source_type=source["type"],
                url=link,
                title=title,
                text=clean_text or title,
                published_at=pub_date,
                collected_at=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
            )
            items.append(item)

        return items

    def fetch_all(self) -> List[RawNewsItem]:
        all_items: List[RawNewsItem] = []
        for src in self.sources:
            try:
                feed_items = self.fetch_feed(src)
                all_items.extend(feed_items)
            except Exception:
                continue
        return all_items

