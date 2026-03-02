import re
import pymorphy3
from loguru import logger

morph = pymorphy3.MorphAnalyzer()


def _normalize(word: str) -> str:
    return morph.parse(word)[0].normal_form


def _lemmatize_text(text: str) -> set:
    words = re.findall(r'[а-яёa-z]+', text.lower())
    return {_normalize(w) for w in words}


def _lemmatize_keywords(keywords_str: str) -> list:
    """Возвращает список уникальных нормализованных ключевых слов/фраз."""
    seen = set()
    result = []
    for kw in keywords_str.split(','):
        words = re.findall(r'[а-яёa-z]+', kw.strip().lower())
        if not words:
            continue
        if len(words) == 1:
            normalized = _normalize(words[0])
        else:
            normalized = tuple(_normalize(w) for w in words)
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


# Широкий набор паттернов: ищу, нужен, бюджет, оплата и т.д.
_ORDER_PATTERNS = re.compile(
    r'ищу|ищем|найду|найдём'
    r'|нужен|нужна|нужно|нужны|нужны|нужного|нужному'
    r'|требуется|требуются|требуем'
    r'|куплю|куплено|покупаю|покупаем'
    r'|хочу|хотим|хотел\s+бы|хотела\s+бы'
    r'|заказ\w*|закажу|заказать|заказываю|заказываем'
    r'|бюджет|стоимость|цена|ценник|прайс'
    r'|оплат\w+|оплачу|оплатим|платим|заплачу|заплатим'
    r'|готов\s+платить|готовы\s+платить|готов\s+заплатить'
    r'|срочно|срочный|срочная|срочное|asap'
    r'|дедлайн|deadline|до\s+\d+|до\s+завтра|до\s+конца'
    r'|нанять|найму|наймём|нанимаю|нанимаем'
    r'|подряд|подрядчик|исполнитель|фрилансер|фриланс'
    r'|есть\s+задач\w+|есть\s+проект\w*|есть\s+работ\w+'
    r'|задача|задание|проект|тз|техзадани\w+'
    r'|помогите|помоги|помоги|помогём'
    r'|кто\s+может|кто\s+умеет|кто\s+занимается|кто\s+делает'
    r'|предложени\w+|предлагайте|откликайтесь|отклик'
    r'|напишите|напиши|пишите|пиши'
    r'|в\s+лс|в\s+личку|в\s+личке|в\s+дм|личные\s+сообщения'
    r'|жду\s+\w+|рассмотрим\s+\w+|рассмотрю\s+\w+'
    r'|сделайте|сделай|разработайте|разработай'
    r'|ищу\s+специалист\w*|ищу\s+мастер\w*|ищу\s+профессионал\w*',
    re.IGNORECASE,
)


def _is_order(text: str) -> bool:
    return bool(_ORDER_PATTERNS.search(text))


def matches_filter(text: str, pos_prompt: str | None, stop_words_str: str | None, min_keywords: int) -> bool:
    snippet = text[:80].replace('\n', ' ')

    # 1. Слишком короткие — пропускаем
    if len(text) < 20:
        logger.debug(f"ФИЛЬТР: отклонено (короткое) | «{snippet}»")
        return False

    text_lower = text.lower()

    # 2. Стоп-слова — быстрая проверка без морфологии
    for sw in (stop_words_str or '').split(','):
        sw = sw.strip().lower()
        if sw and sw in text_lower:
            logger.debug(f"ФИЛЬТР: отклонено (стоп-слово «{sw}») | «{snippet}»")
            return False

    # 3. Морфологический анализ текста
    text_lemmas = _lemmatize_text(text)

    # 4. Считаем совпавшие ключевые слова/фразы
    matched = 0
    matched_kws = []
    for kw in _lemmatize_keywords(pos_prompt or ''):
        if isinstance(kw, tuple):
            if all(w in text_lemmas for w in kw):
                matched += 1
                matched_kws.append(' '.join(kw))
        else:
            if kw in text_lemmas:
                matched += 1
                matched_kws.append(kw)

    logger.debug(f"ФИЛЬТР: совпало {matched}/{min_keywords} ключевых слов {matched_kws} | «{snippet}»")

    if matched < min_keywords:
        return False

    if not _is_order(text):
        logger.debug(f"ФИЛЬТР: отклонено (не похоже на заказ) | «{snippet}»")
        return False

    return True
