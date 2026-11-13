"""SQLAlchemy 2.0 Database Models and Storage Management."""

import datetime
from typing import List, Optional
from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    Float,
    Boolean,
    create_engine,
    select,
    desc
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

Base = declarative_base()


class ProcessedNews(Base):
    __tablename__ = "processed_news"

    news_id = Column(String(64), primary_key=True)
    published_at = Column(String(32), nullable=False)
    collected_at = Column(String(32), nullable=False)
    source_name = Column(String(128), nullable=False)
    source_type = Column(String(64), nullable=False)
    url = Column(String(1024), unique=True, nullable=False)
    main_group = Column(String(16), nullable=False)
    additional_groups = Column(String(64), default="")
    keywords = Column(Text, nullable=False)
    geography = Column(String(128), nullable=False)
    comment = Column(Text, default="")

    # Internal pipeline fields (not exported to the strict final table)
    title = Column(Text, nullable=False)
    cleaned_text = Column(Text, nullable=True)
    source_rank = Column(Float, default=1.0)  # Authority score based on academic research
    cluster_id = Column(String(64), nullable=True)
    is_duplicate = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class DatabaseManager:
    def __init__(self, db_url: str):
        if db_url.startswith("sqlite:///"):
            import os
            from pathlib import Path
            raw_path = db_url.replace("sqlite:///", "")
            # handle windows or relative path
            db_file = Path(raw_path)
            db_file.parent.mkdir(parents=True, exist_ok=True)

        self.engine = create_engine(db_url, echo=False)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()

    def url_exists(self, url: str) -> bool:
        with self.get_session() as session:
            stmt = select(ProcessedNews.news_id).where(ProcessedNews.url == url)
            return session.scalar(stmt) is not None

    def save_news(self, record: ProcessedNews):
        with self.get_session() as session:
            session.merge(record)
            session.commit()

    def get_all_records(self, deduplicated_only: bool = True) -> List[ProcessedNews]:
        with self.get_session() as session:
            stmt = select(ProcessedNews)
            if deduplicated_only:
                stmt = stmt.where(ProcessedNews.is_duplicate.is_(False))
            stmt = stmt.order_by(desc(ProcessedNews.published_at))
            return session.scalars(stmt).all()

