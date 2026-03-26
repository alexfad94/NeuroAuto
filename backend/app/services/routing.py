import re
from typing import Optional


def detect_trigger(message: str, rules: dict) -> Optional[str]:
    text = message.lower()
    words = re.findall(r"\w+", text, flags=re.IGNORECASE)

    def _match_token(token: str) -> bool:
        token = token.lower().strip()
        if not token:
            return False
        # For short tokens (e.g. "то") require exact word match.
        if len(token) <= 3:
            return token in words
        # For normal tokens allow morphological endings via prefix match.
        return any(w.startswith(token) for w in words)

    for item in rules.get("triggers", []):
        for kw in item.get("keywords", []):
            keyword = kw.lower().strip()
            if not keyword:
                continue
            kw_tokens = re.findall(r"\w+", keyword, flags=re.IGNORECASE)
            if not kw_tokens:
                continue

            # Single-token keyword: direct token matching with safe stemming.
            if len(kw_tokens) == 1 and _match_token(kw_tokens[0]):
                return item.get("code")

            # Multi-token keyword: all keyword tokens should be present in the phrase.
            if len(kw_tokens) > 1 and all(_match_token(t) for t in kw_tokens):
                return item.get("code")
    return None


def should_escalate_immediately(message: str, rules: dict) -> bool:
    text = message.lower()
    for kw in rules.get("hard_escalation_keywords", []):
        if kw.lower() in text:
            return True
    return False


def should_route_to_manager(message: str) -> bool:
    """Route only when user asks for direct human follow-up/action."""
    text = message.lower()
    handoff_keywords = [
        "свяжите",
        "перезвоните",
        "передайте менеджеру",
        "передайте рекрутеру",
        "свяжите с рекрутером",
        "хочу с менеджером",
        "запишите меня",
        "оформить заявку",
        "оставлю контакты",
        "хочу оформить",
    ]
    return any(kw in text for kw in handoff_keywords)


def is_positive_confirmation(message: str) -> bool:
    text = message.lower().strip()
    positive_keywords = [
        "да",
        "ок",
        "хорошо",
        "согласен",
        "согласна",
        "давайте",
        "можно",
        "оформляйте",
        "передавайте",
        "передайте рекрутеру",
        "свяжите",
        "перезвоните",
    ]
    return any(kw in text for kw in positive_keywords)


def is_negative_confirmation(message: str) -> bool:
    text = message.lower().strip()
    negative_keywords = ["нет", "не надо", "не нужно", "потом", "пока нет", "отмена"]
    return any(kw in text for kw in negative_keywords)
