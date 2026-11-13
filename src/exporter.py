"""Exporter module for exporting ProcessedNews to CSV, Excel, and JSON datasets.

Ensures strict output compliance with Section 3 of ТЗ:
Columns:
- news_id
- published_at
- collected_at
- source_name
- source_type
- url
- main_group
- additional_groups
- keywords
- geography
- comment
"""

import csv
from pathlib import Path
from typing import List, Union
from src.database.models import ProcessedNews
from src.schemas import FinalNewsRecord, normalize_group_code


COLUMNS = [
    "news_id",
    "published_at",
    "collected_at",
    "source_name",
    "source_type",
    "url",
    "main_group",
    "additional_groups",
    "keywords",
    "geography",
    "comment"
]


def convert_record_to_final(rec: ProcessedNews) -> FinalNewsRecord:
    # Ensure keywords format adheres strictly to '; ' separator
    kw_raw = rec.keywords or ""
    # Normalize keywords separator
    parts = [p.strip().rstrip(";") for p in kw_raw.replace("\n", ";").split(";") if p.strip()]
    formatted_keywords = "; ".join(parts)

    return FinalNewsRecord(
        news_id=rec.news_id,
        published_at=rec.published_at,
        collected_at=rec.collected_at,
        source_name=rec.source_name,
        source_type=rec.source_type,
        url=rec.url,
        main_group=normalize_group_code(rec.main_group),
        additional_groups=rec.additional_groups or "",
        keywords=formatted_keywords,
        geography=rec.geography,
        comment=rec.comment or ""
    )


def export_to_csv(records: List[ProcessedNews], output_path: Union[str, Path]):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, delimiter=";")
        writer.writeheader()

        for rec in records:
            final_item = convert_record_to_final(rec)
            writer.writerow(final_item.model_dump())

