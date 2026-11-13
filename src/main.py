"""CLI entry point for running the news parsing pipeline."""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.pipeline import NewsPipeline
from src.config import settings


def main():
    parser = argparse.ArgumentParser(description="News Parser and Fact Extractor")
    parser.add_argument(
        "--action",
        choices=["run", "collect", "export"],
        default="run",
        help="Action to perform: run (full pipeline), collect, or export"
    )
    parser.add_argument(
        "--no-tg",
        action="store_true",
        help="Skip Telegram channels scraping"
    )
    parser.add_argument(
        "--output",
        default="data/final_news_dataset.csv",
        help="Output CSV path for exported dataset"
    )

    args = parser.parse_args()
    pipeline = NewsPipeline()

    if args.action in ["run", "collect"]:
        raw_items = pipeline.run_collection(include_telegram=not args.no_tg)
        if args.action == "run":
            pipeline.process_items(raw_items)
            out_file = pipeline.export_dataset(args.output)
            print(f"\n[DONE] Finished processing. Dataset saved to {out_file}")
    elif args.action == "export":
        out_file = pipeline.export_dataset(args.output)
        print(f"\n[DONE] Exported database to {out_file}")


if __name__ == "__main__":
    main()

