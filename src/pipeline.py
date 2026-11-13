"""Unified Processing Pipeline for Economic & Real Estate News.

Pipeline stages (according to ТЗ Section 7):
1. Collect publications (RSS feeds, Web pages, Telegram channels).
2. Filter ads and noise without news facts (FirstLineFilter).
3. Cluster and resolve batch duplicates; match against cumulative DB (Deduplicator).
4. Assign main group and optional additional groups (M01-M10, H01-H05).
5. Extract factual keywords ([factor] + [action] + [numbers] + [status] + [subject]).
6. Extract geography and service comments.
7. Save unique items to SQLite/PostgreSQL.
8. Export to clean final dataset (CSV).
"""

import uuid
import logging
from datetime import datetime
from typing import List, Optional
from pathlib import Path

from src.config import settings
from src.schemas import RawNewsItem
from src.database.models import DatabaseManager, ProcessedNews
from src.scrapers.rss_scraper import RSSScraper
from src.scrapers.telegram_scraper import TelegramScraper
from src.processing.filter import FirstLineFilter
from src.processing.deduplicator import Deduplicator, get_source_authority
from src.analysis.llm_annotator import LLMAnnotator
from src.exporter import export_to_csv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("NewsPipeline")


class NewsPipeline:
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager(settings.DATABASE_URL)
        self.filter = FirstLineFilter(ad_threshold=settings.AD_FILTER_THRESHOLD)
        self.deduplicator = Deduplicator(similarity_threshold=settings.SIMILARITY_THRESHOLD)
        self.annotator = LLMAnnotator()

        self.rss_scraper = RSSScraper()
        self.tg_scraper = TelegramScraper()

    def run_collection(self, include_telegram: bool = True) -> List[RawNewsItem]:
        logger.info("Starting collection stage...")
        collected: List[RawNewsItem] = []

        # 1. Fetch RSS
        try:
            rss_items = self.rss_scraper.fetch_all()
            logger.info(f"Collected {len(rss_items)} items from RSS feeds.")
            collected.extend(rss_items)
        except Exception as e:
            logger.error(f"Error fetching RSS: {e}")

        # 2. Fetch Telegram
        if include_telegram:
            try:
                tg_items = self.tg_scraper.fetch_all()
                logger.info(f"Collected {len(tg_items)} items from Telegram channels.")
                collected.extend(tg_items)
            except Exception as e:
                logger.error(f"Error fetching Telegram: {e}")

        return collected

    def process_items(self, raw_items: List[RawNewsItem]) -> List[ProcessedNews]:
        logger.info(f"Starting processing stage for {len(raw_items)} items...")

        # Step 1: Pre-filter already existing URLs
        new_items = []
        for item in raw_items:
            if not self.db.url_exists(item.url):
                new_items.append(item)
            else:
                logger.debug(f"Skipping already existing URL: {item.url}")

        logger.info(f"{len(new_items)} items are new to database.")

        # Step 2: First-line Ad & Noise Filtering
        clean_batch = []
        for item in new_items:
            is_ad, score, reason = self.filter.evaluate(item.title, item.text)
            if is_ad:
                logger.info(f"Filtered out as ad/garbage: '{item.title}' (Reason: {reason})")
                continue
            cleaned_text = self.filter.clean_text(item.text)
            clean_batch.append((item, cleaned_text))

        logger.info(f"{len(clean_batch)} items passed first-line ad filter.")

        # Step 3: Cluster and deduplicate inside current batch
        batch_dicts = []
        for item, cleaned_text in clean_batch:
            batch_dicts.append({
                "item": item,
                "title": item.title,
                "text": cleaned_text,
                "url": item.url,
                "source_name": item.source_name,
                "source_type": item.source_type.value,
                "published_at": item.published_at,
            })

        batch_unique_dicts = self.deduplicator.cluster_and_resolve_batch(batch_dicts)
        logger.info(f"{len(batch_unique_dicts)} items remain after intra-batch deduplication.")

        # Step 4: Compare against cumulative database
        existing_records_raw = self.db.get_all_records(deduplicated_only=True)
        existing_records = [
            {
                "news_id": r.news_id,
                "title": r.title,
                "keywords": r.keywords,
                "published_at": r.published_at,
                "source_rank": r.source_rank,
            }
            for r in existing_records_raw
        ]

        processed_news_list: List[ProcessedNews] = []
        for b_dict in batch_unique_dicts:
            item: RawNewsItem = b_dict["item"]
            cleaned_text: str = b_dict["text"]

            # Check duplicate against cumulative storage
            dup_match = self.deduplicator.find_duplicate_in_existing(
                candidate_title=item.title,
                candidate_text=cleaned_text,
                existing_records=existing_records
            )
            if dup_match:
                match_rec, sim = dup_match
                logger.info(
                    f"Duplicate found in DB for '{item.title}': "
                    f"matches '{match_rec['title']}' (similarity: {sim:.2f}). Skipping as per ТЗ Section 5."
                )
                continue

            # Step 5: LLM Annotation (Rubric group, keywords, geography, fact validation)
            annotation = self.annotator.annotate(
                title=item.title,
                text=cleaned_text,
                source_name=item.source_name,
                published_at=item.published_at
            )
            if not annotation:
                continue

            if annotation.is_advertisement:
                logger.info(f"LLM identified promotional content without fact: '{item.title}'")
                continue

            # Format additional groups as comma separated string
            add_groups_str = ", ".join(annotation.additional_groups) if annotation.additional_groups else ""
            keywords_str = "; ".join(annotation.keywords)

            source_rank = get_source_authority(item.source_name, item.source_type.value, item.url)
            collected_at_str = item.collected_at or datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

            record = ProcessedNews(
                news_id=str(uuid.uuid4()),
                published_at=item.published_at,
                collected_at=collected_at_str,
                source_name=item.source_name,
                source_type=item.source_type.value,
                url=item.url,
                main_group=annotation.main_group,
                additional_groups=add_groups_str,
                keywords=keywords_str,
                geography=annotation.geography,
                comment=annotation.service_comment or "",
                title=item.title,
                cleaned_text=cleaned_text,
                source_rank=source_rank,
                is_duplicate=False
            )

            self.db.save_news(record)
            processed_news_list.append(record)
            # Add to local existing cache to catch duplicates later in the same run
            existing_records.append({
                "news_id": record.news_id,
                "title": record.title,
                "keywords": record.keywords,
                "published_at": record.published_at,
                "source_rank": record.source_rank
            })

        logger.info(f"Successfully processed and stored {len(processed_news_list)} unique records.")
        return processed_news_list

    def export_dataset(self, output_path: str = "data/dataset.csv") -> Path:
        all_unique = self.db.get_all_records(deduplicated_only=True)
        export_path = Path(output_path)
        export_to_csv(all_unique, export_path)
        logger.info(f"Exported {len(all_unique)} records to {export_path.resolve()}")
        return export_path

