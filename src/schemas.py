"""Core data schemas according to Technical Specifications (ТЗ).

Dataset Columns required:
- news_id (str / UUID)
- published_at (ISO datetime or Date; if time is unknown, date only without assuming time)
- collected_at (ISO datetime)
- source_name (name of media, channel, agency)
- source_type (официальный источник | СМИ | компания | Telegram-канал)
- url (direct publication link)
- main_group (code from rubricator M01-M10, N01-N05)
- additional_groups (comma-separated codes or empty string)
- keywords (5-10 factual phrases separated by '; ')
- geography (country, RF subject, city)
- comment (service note only or empty string)
"""

from enum import Enum
import re
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class RubricGroup(str, Enum):
    # Macroeconomic groups (M01–M10) - Latin M and Cyrillic М support
    M01 = "M01"  # Денежно-кредитная политика (ставка ЦБ, требования)
    M02 = "M02"  # Кредитование и сбережения (потреб/корп кредиты, вклады. Ипотека НЕ СЮДА)
    M03 = "M03"  # Инфляция (ИПЦ, ожидания, прогнозы)
    M04 = "M04"  # Доходы и занятость (зарплаты, доходы, безработица)
    M05 = "M05"  # Экономическая активность (ВВП, промпроизводство, инвестиции)
    M06 = "M06"  # Валютный рынок (курсы валют, валютные ограничения)
    M07 = "M07"  # Внешняя торговля и санкции (экспорт, импорт, логистика, пошлины)
    M08 = "M08"  # Бюджет и господдержка (налоги, субсидии, маткапитал. Льготная ипотека в H02)
    M09 = "M09"  # Демография и миграция (рождаемость, миграция, домохозяйства)
    M10 = "M10"  # Сырье, энергия и транспорт (нефть, газ, тарифы. Стройматериалы в H04)

    # Real Estate & Construction groups (H01–H05)
    H01 = "H01"  # Рыночная ипотека (ставки без льгот, первоначальный взнос)
    H02 = "H02"  # Льготные жилищные программы (Семейная, IT-ипотека, лимиты)
    H03 = "H03"  # Рынок жилья (цены, спрос, продажи, скидки, рассрочки)
    H04 = "H04"  # Строительство (себестоимость, эскроу, ввод жилья, стройматериалы)
    H05 = "H05"  # Территория и инфраструктура (дороги, школы, благоустройство)


def normalize_group_code(code: str) -> str:
    """Normalizes Cyrillic М/Н to Latin M/H for consistent canonical storage."""
    code = code.strip().upper()
    code = code.replace("М", "M").replace("Н", "H")
    return code


class SourceType(str, Enum):
    OFFICIAL = "официальный источник"
    MEDIA = "СМИ"
    COMPANY = "компания"
    TELEGRAM = "Telegram-канал"


class RawNewsItem(BaseModel):
    """Raw scraped news item before processing."""
    source_name: str
    source_type: SourceType
    url: str
    title: str
    text: str
    published_at: str  # ISO string or YYYY-MM-DD
    collected_at: Optional[str] = None
    author: Optional[str] = None
    media_urls: List[str] = Field(default_factory=list)


class LLMNewsAnnotation(BaseModel):
    """Structured output expected from LLM."""
    main_group: str = Field(
        ...,
        description="Код основной тематической группы (M01-M10 или H01-H05)"
    )
    additional_groups: List[str] = Field(
        default_factory=list,
        description="Дополнительные коды групп (M01-M10, H01-H05), если новость затрагивает несколько тем"
    )
    keywords: List[str] = Field(
        ...,
        description="От 5 до 10 фактологических ключевых фраз по формуле: [фактор] + [действие/направление] + [числа с ед. изм.] + [статус] + [субъект]. Запрещены пустые слова."
    )
    geography: str = Field(
        ...,
        description="Страна, субъект РФ, город события (например: 'Россия, Челябинская область, Челябинск' или 'Россия'). Не путать с местом редакции."
    )
    is_advertisement: bool = Field(
        False,
        description="Является ли новость пустой рекламой, промо-акцией или инфошумом без реального факта"
    )
    service_comment: Optional[str] = Field(
        "",
        description="ИСКЛЮЧИТЕЛЬНО служебные пометки (битая ссылка, неточное время, спорная рубрикация). Запрещен пересказ."
    )

    @field_validator("main_group")
    @classmethod
    def validate_main_group(cls, v: str) -> str:
        return normalize_group_code(v)

    @field_validator("additional_groups")
    @classmethod
    def validate_additional_groups(cls, v: List[str]) -> List[str]:
        return [normalize_group_code(g) for g in v if g.strip()]

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, v: List[str]) -> List[str]:
        banned = {"новость", "ситуация", "эксперты", "рынок"}
        cleaned = []
        for kw in v:
            kw_clean = kw.strip().rstrip(";")
            if kw_clean.lower() not in banned and len(kw_clean) > 3:
                cleaned.append(kw_clean)
        return cleaned


class FinalNewsRecord(BaseModel):
    """Final validated record for the dataset conforming strictly to the assignment schema."""
    news_id: str
    published_at: str
    collected_at: str
    source_name: str
    source_type: str
    url: str
    main_group: str
    additional_groups: str = ""
    keywords: str
    geography: str
    comment: str = ""

    @model_validator(mode="after")
    def validate_rules(self):
        # Validate main group
        valid_groups = {g.value for g in RubricGroup}
        norm_main = normalize_group_code(self.main_group)
        if norm_main not in valid_groups:
            raise ValueError(f"Invalid main_group '{self.main_group}'. Must be one of {valid_groups}")

        # Validate additional groups formatting
        if self.additional_groups:
            norm_add = []
            for g in self.additional_groups.split(","):
                g = g.strip()
                if g:
                    ng = normalize_group_code(g)
                    if ng not in valid_groups:
                        raise ValueError(f"Invalid additional group '{g}'")
                    norm_add.append(ng)

        # Validate keywords: must be 5-10 separated by '; '
        kw_list = [k.strip() for k in self.keywords.split(";") if k.strip()]
        if not (5 <= len(kw_list) <= 10):
            raise ValueError(f"Keywords count must be between 5 and 10, got {len(kw_list)}: '{self.keywords}'")

        # Check banned generic words as standalone keywords
        banned_words = {"новость", "ситуация", "эксперты", "рынок"}
        for k in kw_list:
            if k.lower() in banned_words:
                raise ValueError(f"Banned standalone generic keyword found: '{k}'")

        return self
