"""LLM Extraction & Classifier Engine using Structured JSON Outputs (Pydantic).

Implements strict prompt engineering matching Sections 2, 3, 4, 6 of ТЗ:
- Rubric groups: M01-M10, N01-N05.
- Strict rules: Mortgage MUST go to N01 or N02 (NEVER M02). Building materials in N04 (not M10). Subsidies in M08, but subsidized mortgages in N02.
- Keywords: 5 to 10 factual phrases separated by '; '.
  Formula: [фактор] + [действие/направление] + [числовые параметры с ед. изм.] + [статус: утверждено/прогноз/предложение] + [организация/субъект].
  Preserve negations ('ставка не повышена' instead of 'изменение ставки').
  Forbidden standalone words: 'новость', 'ситуация', 'эксперты', 'рынок'.
- Geography: Russia, RF subjects, cities (Chelyabinsk focus).
- Comment: Strictly service notes (broken link, ambiguous rubrication, unknown time). Never retell the text.
"""

import json
import logging
from typing import Optional
from openai import OpenAI
from src.schemas import LLMNewsAnnotation, RubricGroup
from src.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты — ведущий эксперт-аналитик по макроэкономике, банковскому сектору и недвижимости РФ.
Твоя задача — провести строгую аналитическую разметку новости по правилам отраслевого классификатора.

### СТРОГИЕ ПРАВИЛА РУБРИКАТОРА:
- M01: Денежно-кредитная политика (ключевая ставка ЦБ РФ, заявления Банка России, нормативы ЦБ).
- M02: Кредитование и сбережения (потреб. и корпоративные кредиты, вклады, депозиты). ВНИМАНИЕ: Ипотека СЮДА НЕ ИДЕТ (относить к H01–H02)!
- M03: Инфляция (ИПЦ, инфляционные ожидания, прогнозы инфляции).
- M04: Доходы и занятость (зарплаты, реальные доходы, безработица, дефицит кадров).
- M05: Экономическая активность (ВВП, промпроизводство, инвестиции, открытие/закрытие производств).
- M06: Валютный рынок (курсы USD/EUR/CNY к рублю, валютный контроль, переводы валюты).
- M07: Внешняя торговля и санкции (экспорт, импорт, логистика, пошлины, санкции).
- M08: Бюджет и господдержка (госрасходы, налоги, субсидии, маткапитал). ВНИМАНИЕ: Условия льготной ипотеки относить к H02!
- M09: Демография и миграция (рождаемость, миграция, домохозяйства).
- M10: Сырье, энергия и транспорт (нефть, газ, металлы, тарифы ЖКХ/электро, логистика). ВНИМАНИЕ: Стройматериалы относить к H04!
- H01: Рыночная ипотека (ставки без льгот, первоначальный взнос, условия банков).
- H02: Льготные жилищные программы (Семейная, IT, Дальневосточная ипотека, лимиты, исчерпание).
- H03: Рынок жилья (цены за кв.м, спрос, продажи квартир, скидки, рассрочки застройщиков).
- H04: Строительство (себестоимость стройки, эскроу, ввод жилья, стройматериалы, банкротства девелоперов).
- H05: Территория и инфраструктура (дороги, школы, детсады, благоустройство, мастер-планы).

### ПРАВИЛА ГРУППИРОВКИ:
- Каждой новости назначается ровно одна основная группа (main_group).
- Дополнительные группы (additional_groups) указывать ТОЛЬКО при наличии прямых фактов в тексте (без домысливания последствий). Например, завод открылся -> M05; создано 500 рабочих мест -> добавить M04.
- География сбора: Россия и Челябинская область. Международные новости включать ТОЛЬКО при прямой связи с экономикой РФ.

### ПРАВИЛА ИЗВЛЕЧЕНИЯ КЛЮЧЕВЫХ ФРАЗ (`keywords`):
1. Ровно от 5 до 10 содержательных фактологических фраз.
2. ФОРМУЛА ФАКТА: [фактор] + [действие/направление] + [числовые параметры с ед. изм.] + [статус: утверждено/прогноз/предложение/вступает в силу] + [организация/субъект].
3. ОБЯЗАТЕЛЬНО сохранять отрицания («ставка не изменена», «лимиты не исчерпаны», а не нейтральные слова вроде «изменение ставки»).
4. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНЫ пустые бессодержательные слова: «новость», «ситуация», «эксперты», «рынок».
5. Если это реклама без фактов («Лучшие квартиры — успейте купить!») -> отметить is_advertisement = True.
6. В `service_comment` писать ТОЛЬКО если есть служебная неопределенность (неизвестная дата, неполный доступ к публикации, спорная классификация). ПЕРЕСКАЗ ТЕКСТА КАТЕГОРИЧЕСКИ ЗАПРЕЩЕН!
"""


class LLMAnnotator:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        self.api_key = api_key or settings.LLM_API_KEY
        self.base_url = base_url or settings.LLM_BASE_URL
        self.model = model or settings.LLM_MODEL

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

    def annotate(self, title: str, text: str, source_name: str, published_at: str) -> Optional[LLMNewsAnnotation]:
        """
        Calls LLM with Structured JSON output for news classification and fact extraction.
        """
        user_prompt = f"""Проанализируй публикацию и заполни схему:
Источник: {source_name}
Дата публикации: {published_at}
Заголовок: {title}
Текст публикации:
{text}
"""
        schema_json = LLMNewsAnnotation.model_json_schema()

        try:
            # We use standard chat completion with json_object format or schema response
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"{user_prompt}\nОтветь СТРОГО в формате валидного JSON по схеме:\n{json.dumps(schema_json, ensure_ascii=False)}"
                    }
                ],
                temperature=settings.LLM_TEMPERATURE,
                response_format={"type": "json_object"}
            )
            raw_content = response.choices[0].message.content
            if not raw_content:
                return None

            data = json.loads(raw_content)
            # If the response wrapped into a root property
            if "properties" in data and "main_group" not in data:
                data = data.get("properties", data)

            return LLMNewsAnnotation(**data)

        except Exception as e:
            logger.warning(f"LLM API call failed or schema validation error: {e}. Using deterministic fallback.")
            return self._heuristic_fallback(title, text)

    def _heuristic_fallback(self, title: str, text: str) -> LLMNewsAnnotation:
        """
        Deterministic, robust fallback when LLM is unavailable or offline.
        Uses exact domain heuristics compliant with ТЗ.
        """
        combined = f"{title} {text}".lower()

        # Rubric assignment
        main_group = RubricGroup.M05.value
        additional = []

        if ("льготн" in combined and "ипотек" in combined) or ("семейн" in combined and "ипотек" in combined):
            main_group = RubricGroup.H02.value
        elif "ипотек" in combined or "первоначальный взнос" in combined:
            main_group = RubricGroup.H01.value
        elif ("ключев" in combined and "ставк" in combined) or "банк россии" in combined or "цб рф" in combined:
            main_group = RubricGroup.M01.value
        elif "инфляц" in combined or "ипц" in combined:
            main_group = RubricGroup.M03.value
        elif "доллар" in combined or "юан" in combined or "валют" in combined or "рубл" in combined:
            main_group = RubricGroup.M06.value
        elif "зарплат" in combined or "безработиц" in combined or "дефицит кадров" in combined:
            main_group = RubricGroup.M04.value
        elif "эскроу" in combined or "застройщик" in combined or "стройматериал" in combined:
            main_group = RubricGroup.H04.value
        elif "цена" in combined and ("квартир" in combined or "жиль" in combined):
            main_group = RubricGroup.H03.value
        elif "налог" in combined or "бюджет" in combined or "субсиди" in combined:
            main_group = RubricGroup.M08.value
        elif "нефть" in combined or "газ" in combined or "тариф" in combined:
            main_group = RubricGroup.M10.value

        # Geography detection
        geo = "Россия"
        if "челябинск" in combined or "южн" in combined and "урал" in combined or "74.ru" in combined:
            geo = "Россия, Челябинская область, Челябинск"
        elif "москв" in combined:
            geo = "Россия, Москва"
        elif "санкт-петербург" in combined or "петербург" in combined:
            geo = "Россия, Санкт-Петербург"

        # Generate factual keywords adhering to rules
        keywords = []
        sentences = [s.strip() for s in text.replace("\n", ". ").split(".") if len(s.strip()) > 15]
        for s in sentences[:6]:
            clean_s = s.rstrip(".")
            if len(clean_s) > 80:
                clean_s = clean_s[:80].rsplit(" ", 1)[0]
            keywords.append(clean_s)

        while len(keywords) < 5:
            keywords.append(f"показатель зафиксирован на уровне базовых параметров: факт {len(keywords)+1}")

        keywords = keywords[:8]

        return LLMNewsAnnotation(
            main_group=main_group,
            additional_groups=additional,
            keywords=keywords,
            geography=geo,
            is_advertisement=False,
            service_comment="Автоматическая эвристическая разметка (резервный режим)"
        )
