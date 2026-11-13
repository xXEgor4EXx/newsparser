from src.processing.filter import FirstLineFilter
from src.processing.deduplicator import Deduplicator, get_source_authority


def test_ad_filter_pure_ad():
    flt = FirstLineFilter()
    title = "Лучшие квартиры — успейте купить прямо сейчас!"
    text = "Только сегодня шок-цена на квартиры в новостройке. Скидка до 20%! Звоните прямо сейчас, успейте купить!"
    is_ad, score, reason = flt.evaluate(title, text)
    assert is_ad is True
    assert score > 0.5


def test_ad_filter_realty_conditions_preserved():
    flt = FirstLineFilter()
    title = "Застройщик изменил условия рассрочки: новый срок и первоначальный взнос"
    text = "Строительная компания запустила программу рассрочки на квартиры с первоначальным взносом 20% и процентной ставкой 0% на 2 года."
    is_ad, score, reason = flt.evaluate(title, text)
    assert is_ad is False


def test_source_authority():
    cbr_auth = get_source_authority("Банк России", "официальный источник", "https://cbr.ru/press")
    rbc_auth = get_source_authority("РБК", "СМИ", "https://rbc.ru/economics")
    tg_auth = get_source_authority("@tg_news", "Telegram-канал", "https://t.me/tg_news/1")

    assert cbr_auth > rbc_auth
    assert rbc_auth > tg_auth


def test_deduplicator_intra_batch():
    dedup = Deduplicator(similarity_threshold=0.38)
    items = [
        {
            "title": "Банк России повысил ключевую ставку до 21% годовых",
            "text": "Совет директоров Банка России принял решение повысить ключевую ставку на 200 б.п. до 21% годовых.",
            "source_name": "РБК",
            "source_type": "СМИ",
            "url": "https://rbc.ru/1",
            "published_at": "2026-11-11T13:35:00"
        },
        {
            "title": "ЦБ РФ повысил ключевую ставку до 21 процента",
            "text": "Банк России повысил ставку до рекордных 21% годовых для борьбы с высокой инфляцией.",
            "source_name": "Банк России",
            "source_type": "официальный источник",
            "url": "https://cbr.ru/press/1",
            "published_at": "2026-11-11T13:30:00"
        }
    ]

    reps = dedup.cluster_and_resolve_batch(items)
    # The two articles are duplicates of the same event; official CBR should be chosen as primary source
    assert len(reps) == 1
    assert reps[0]["source_name"] == "Банк России"

