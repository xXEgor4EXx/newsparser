import pytest
from pydantic import ValidationError
from src.schemas import (
    FinalNewsRecord,
    RubricGroup,
    normalize_group_code,
    LLMNewsAnnotation
)


def test_rubric_code_normalization():
    assert normalize_group_code("М01") == "M01"
    assert normalize_group_code("m01") == "M01"
    assert normalize_group_code("Н02") == "H02"
    assert normalize_group_code("h05") == "H05"


def test_final_news_record_valid():
    rec = FinalNewsRecord(
        news_id="test-123",
        published_at="2026-11-11T12:00:00",
        collected_at="2026-11-11T12:05:00",
        source_name="Банк России",
        source_type="официальный источник",
        url="https://cbr.ru/press/1",
        main_group="M01",
        additional_groups="",
        keywords="ключевая ставка; сохранение на уровне 21%; заседание Совета директоров; Банк России; ноябрь 2026; инфляционное давление",
        geography="Россия",
        comment=""
    )
    assert rec.main_group == "M01"
    assert len(rec.keywords.split(";")) == 6


def test_final_news_record_invalid_group():
    with pytest.raises(ValidationError):
        FinalNewsRecord(
            news_id="test-err",
            published_at="2026-11-11",
            collected_at="2026-11-11",
            source_name="СМИ",
            source_type="СМИ",
            url="https://example.com",
            main_group="INVALID_CODE",
            additional_groups="",
            keywords="фраза один; фраза два; фраза три; фраза четыре; фраза пять",
            geography="Россия"
        )


def test_final_news_record_banned_standalone_keywords():
    with pytest.raises(ValidationError):
        FinalNewsRecord(
            news_id="test-banned",
            published_at="2026-11-11",
            collected_at="2026-11-11",
            source_name="СМИ",
            source_type="СМИ",
            url="https://example.com/2",
            main_group="M03",
            keywords="инфляция; новость; рост цен; потребительская корзина; Росстат",
            geography="Россия"
        )


def test_final_news_record_keyword_count_boundaries():
    # Less than 5 keywords should fail
    with pytest.raises(ValidationError):
        FinalNewsRecord(
            news_id="test-short",
            published_at="2026-11-11",
            collected_at="2026-11-11",
            source_name="СМИ",
            source_type="СМИ",
            url="https://example.com/3",
            main_group="M03",
            keywords="ставка ЦБ; инфляция; Росстат",
            geography="Россия"
        )

