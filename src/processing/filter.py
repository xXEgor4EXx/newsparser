"""First-line Filter for Ads, Clickbait, and Garbage.

Follows Section 6 of the Technical Specifications (ТЗ):
- Exclude materials with purely promotional goals without real news facts.
- Exclude call to actions ('купить', 'подписаться', 'оставить заявку').
- Exclude commercial digests without facts.
- Retain company announcements IF they contain concrete facts (e.g., mortgage installment changes,
  launch of a facility, pricing facts).
"""

import re
from typing import Tuple, List

# Explicit advertising call-to-actions
BANNED_AD_PATTERNS = [
    r"успей(?:те)?\s+купить",
    r"только\s+сегодня",
    r"шок-?цена",
    r"подпиши(?:сь|тесь)\s+на\s+канал",
    r"переходи(?:те)?\s+по\s+ссылке",
    r"скидк[аи]\s+до\s+\d+%",
    r"остав(?:ьте|ий)\s+заявку",
    r"звоните\s+прямо\s+сейчас",
    r"лучшие\s+квартиры\s*[-–—]\s*успейте",
    r"подробности\s+по\s+телефону",
    r"акция\s+действует\s+до",
    r"промокод",
    r"бесплатная\s+консультация",
    r"erid:[a-zA-Z0-9]+",  # Russian advertising marker (токен маркировки)
    r"реклама\.\s*ооо",
    r"на\s+правах\s+рекламы",
]

# Markers of valuable economic facts (even if published by commercial companies)
FACT_INDICATORS = [
    r"повысил(?:а|и)?",
    r"снизил(?:а|и)?",
    r"изменил(?:а|и)?\s+условия",
    r"ввел(?:а|и)?",
    r"запустил(?:а|и)?",
    r"первоначальный\s+взнос",
    r"процентн[ая|ой|ую]\s+ставк",
    r"рассрочк[а|и]",
    r"инфляци",
    r"ввп",
    r"цб\s+рф",
    r"банка\s+россии",
    r"ключев[ая|ой]\s+ставк",
    r"инвестици",
    r"ввод\s+жилья",
    r"строительств",
]


class FirstLineFilter:
    def __init__(self, ad_threshold: float = 0.5):
        self.ad_threshold = ad_threshold
        self.compiled_ad_patterns = [re.compile(p, re.IGNORECASE) for p in BANNED_AD_PATTERNS]
        self.compiled_fact_patterns = [re.compile(p, re.IGNORECASE) for p in FACT_INDICATORS]

    def evaluate(self, title: str, text: str) -> Tuple[bool, float, str]:
        """
        Evaluates whether a text is garbage/ad.
        Returns:
            (is_ad: bool, score: float, reason: str)
        """
        combined = f"{title} {text}".strip()
        if len(combined) < 40:
            return True, 1.0, "Too short (< 40 characters)"

        ad_matches: List[str] = []
        for pattern in self.compiled_ad_patterns:
            found = pattern.findall(combined)
            if found:
                ad_matches.append(found[0])

        fact_matches: List[str] = []
        for pattern in self.compiled_fact_patterns:
            found = pattern.findall(combined)
            if found:
                fact_matches.append(found[0])

        # Advertising markers like erid or 'на правах рекламы' with zero new facts
        has_ad_tag = bool(re.search(r"(?:erid:|на правах рекламы|реклама\.\s*(?:ооо|зао|пао))", combined, re.IGNORECASE))

        # Scoring
        ad_score = min(1.0, len(ad_matches) * 0.35 + (0.5 if has_ad_tag else 0.0))
        fact_bonus = min(0.6, len(fact_matches) * 0.15)
        final_score = max(0.0, ad_score - fact_bonus)

        # Check pure promotional phrases without conditions (e.g. "Лучшие квартиры — успейте купить!")
        if any(re.search(r"лучшие\s+квартиры|успей(?:те)?\s+купить", m, re.IGNORECASE) for m in ad_matches) and len(fact_matches) == 0:
            return True, 0.95, "Pure promotional CTA without facts"

        if has_ad_tag and len(fact_matches) == 0:
            return True, 0.9, "Sponsored post with no substantive economic facts"

        is_ad = final_score >= self.ad_threshold
        reason = f"Ad score {final_score:.2f} (matches: {len(ad_matches)}, facts: {len(fact_matches)})"
        return is_ad, final_score, reason

    def clean_text(self, text: str) -> str:
        """Removes markup tags, multiple spaces and promotional trailing links."""
        # Remove markdown/html links
        cleaned = re.sub(r"https?://\S+", "", text)
        cleaned = re.sub(r"t\.me/\S+", "", cleaned)
        # Remove erid tags
        cleaned = re.sub(r"erid:\s*[a-zA-Z0-9]+", "", cleaned, flags=re.IGNORECASE)
        # Normalize whitespace
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

