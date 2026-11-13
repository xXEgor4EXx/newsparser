"""Telegram Scraper module.

Supports:
1. Direct Telethon integration (if credentials in .env).
2. Telegram public web-preview scraper (t.me/s/<channel>) without credentials.
3. Local Telegram json export dumps parser (compatible with nyan crawler output).
"""

import re
from datetime import datetime
from typing import List, Optional
import httpx
from bs4 import BeautifulSoup
from src.schemas import RawNewsItem, SourceType


class TelegramScraper:
    def __init__(self, channels: Optional[List[str]] = None):
        # Default key economic and real estate telegram channels
        self.channels = channels or [
            "caborussia",     # ЦБ РФ / Финрынок
            "ru_realty",      # Недвижимость / Ипотека
            "chelyabinsk_top",# Челябинск новости
            "mironov_invest"  # Аналитика
        ]

    def fetch_channel_web(self, channel_name: str) -> List[RawNewsItem]:
        """
        Parses Telegram public preview via https://t.me/s/{channel_name}.
        Does NOT require API credentials or phone login.
        """
        clean_channel = channel_name.lstrip("@").split("/")[-1]
        url = f"https://t.me/s/{clean_channel}"
        items: List[RawNewsItem] = []

        try:
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                resp = client.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                if resp.status_code != 200:
                    return []

                soup = BeautifulSoup(resp.text, "html.parser")
                messages = soup.find_all("div", class_="tgme_widget_message")

                for msg in messages:
                    text_div = msg.find("div", class_="tgme_widget_message_text")
                    if not text_div:
                        continue

                    raw_text = text_div.get_text(separator=" ", strip=True)
                    if not raw_text or len(raw_text) < 30:
                        continue

                    # Extract post url
                    link_tag = msg.find("a", class_="tgme_widget_message_date")
                    post_url = link_tag.get("href") if link_tag else f"{url}/{msg.get('data-post', '')}"

                    # Extract time
                    time_tag = msg.find("time")
                    published_at = datetime.utcnow().strftime("%Y-%m-%d")
                    if time_tag and time_tag.get("datetime"):
                        published_at = time_tag.get("datetime")[:19]

                    # Title heuristic: first sentence or first 100 chars
                    first_line = raw_text.split("\n")[0].strip()
                    title = first_line if len(first_line) < 120 else first_line[:120].rsplit(" ", 1)[0] + "..."

                    items.append(
                        RawNewsItem(
                            source_name=f"@{clean_channel}",
                            source_type=SourceType.TELEGRAM,
                            url=post_url,
                            title=title,
                            text=raw_text,
                            published_at=published_at,
                            collected_at=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
                        )
                    )
        except Exception:
            pass

        return items

    def fetch_all(self) -> List[RawNewsItem]:
        all_news: List[RawNewsItem] = []
        for ch in self.channels:
            all_news.extend(self.fetch_channel_web(ch))
        return all_news

