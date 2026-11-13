"""Deduplication Engine based on Section 5 of ТЗ and nyan repository clustering ideas.

Rules from Section 5:
- Match publications by event, participants, dates, and essential conditions (not just exact titles).
- Duplicate definitions:
  * Same publication gathered multiple times.
  * Reprints (перепечатки).
  * Retellings of the same event without substantial new facts.
- Select exactly ONE record per unique event, preferably pointing to the original source (первоисточник)
  or the most complete verifiable publication.
- Distinguish updates: Substantial updates (e.g. proposal -> adoption -> cancellation) ARE separate news.
- Never record the full original text into the final exported dataset.
- Always check duplicates across the entire cumulative database, not just within the current batch.
"""

from typing import List, Tuple, Dict, Any, Optional
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import re


# Source authority scoring based on CyberLeninka paper principles
# Official sources have highest priority as primary originators
SOURCE_AUTHORITY = {
    "cbr.ru": 1.0,
    "kremlin.ru": 1.0,
    "government.ru": 1.0,
    "minfin.gov.ru": 1.0,
    "rosstat.gov.ru": 1.0,
    "дом.рф": 0.95,
    "интерфакс": 0.9,
    "тасс": 0.9,
    "риа новости": 0.88,
    "коммерсантъ": 0.88,
    "ведомости": 0.88,
    "рбк": 0.87,
    "74.ru": 0.80,
    "Telegram-канал": 0.70,
    "default": 0.75,
}


def get_source_authority(source_name: str, source_type: str, url: str) -> float:
    name_lower = source_name.lower()
    url_lower = url.lower()
    for key, score in SOURCE_AUTHORITY.items():
        if key in name_lower or key in url_lower:
            return score
    if source_type == "официальный источник":
        return 0.95
    elif source_type == "СМИ":
        return 0.85
    elif source_type == "Telegram-канал":
        return 0.70
    return SOURCE_AUTHORITY["default"]


class Deduplicator:
    def __init__(self, similarity_threshold: float = 0.38):
        self.similarity_threshold = similarity_threshold
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            max_df=1.0,
            min_df=1,
            sublinear_tf=True
        )

    def extract_key_tokens(self, text: str) -> str:
        """Tokenize, normalize synonyms (e.g. ЦБ РФ -> банк россии) and numbers for semantic event matching."""
        normalized = text.lower()
        normalized = re.sub(r"\bцб(?:\s+рф)?\b", "банк россии", normalized)
        normalized = re.sub(r"\bпроцент(?:а|ов)?\b", "%", normalized)
        normalized = re.sub(r"\bгодовых\b", "", normalized)
        tokens = re.findall(r"\b[а-яa-z0-9%.,-]+\b", normalized)
        return " ".join(tokens)

    def find_duplicate_in_existing(
        self,
        candidate_title: str,
        candidate_text: str,
        existing_records: List[Dict[str, Any]]
    ) -> Optional[Tuple[Dict[str, Any], float]]:
        """
        Compares new candidate with all existing records in the database.
        Returns:
            (best_match_record, similarity_score) if score >= threshold, else None.
        """
        if not existing_records:
            return None

        cand_content = f"{candidate_title} {candidate_text}"
        cand_tokens = self.extract_key_tokens(cand_content)

        corpus = [cand_tokens]
        for rec in existing_records:
            t = rec.get("title", "")
            kw = rec.get("keywords", "")
            rec_content = f"{t} {kw}"
            corpus.append(self.extract_key_tokens(rec_content))

        try:
            tfidf_matrix = self.vectorizer.fit_transform(corpus)
            cand_vec = tfidf_matrix[0:1]
            existing_vecs = tfidf_matrix[1:]
            sims = cosine_similarity(cand_vec, existing_vecs)[0]

            best_idx = int(np.argmax(sims))
            best_score = float(sims[best_idx])

            if best_score >= self.similarity_threshold:
                return existing_records[best_idx], best_score
        except Exception:
            return None

        return None

    def cluster_and_resolve_batch(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Deduplicates a fresh batch of scraped items among themselves:
        Clusters them, chooses the best primary source (highest authority / earliest pub_date).
        Returns only the representative unique items.
        """
        if len(items) <= 1:
            return items

        texts = [self.extract_key_tokens(f"{it['title']} {it.get('text', '')}") for it in items]
        try:
            tfidf = self.vectorizer.fit_transform(texts)
            sim_matrix = cosine_similarity(tfidf)
        except Exception:
            return items

        n = len(items)
        visited = [False] * n
        unique_reps = []

        for i in range(n):
            if visited[i]:
                continue
            cluster = [i]
            visited[i] = True
            for j in range(i + 1, n):
                if not visited[j] and sim_matrix[i, j] >= self.similarity_threshold:
                    cluster.append(j)
                    visited[j] = True

            # Pick best representative from cluster:
            # 1. Highest authority score
            # 2. Earliest publication date
            # 3. Longest/most informative content
            def sort_key(idx: int):
                item = items[idx]
                auth = get_source_authority(
                    item.get("source_name", ""),
                    item.get("source_type", ""),
                    item.get("url", "")
                )
                pub = item.get("published_at", "")
                length = len(item.get("text", ""))
                return (auth, -len(pub), length)

            cluster.sort(key=sort_key, reverse=True)
            chosen_rep = items[cluster[0]]
            unique_reps.append(chosen_rep)

        return unique_reps

