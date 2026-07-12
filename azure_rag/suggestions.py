from typing import TypedDict


SUGGESTION_LIMIT = 4
SUGGESTION_TITLE_QUERY_TOP = 100


class ChatSuggestion(TypedDict):
    title: str
    message: str


def normalize_document_title(title: str) -> str | None:
    normalized = " ".join(title.split())
    return normalized or None


def dedupe_titles(titles: list[str]) -> list[str]:
    unique: dict[str, str] = {}
    for title in titles:
        normalized = normalize_document_title(title)
        if normalized is not None:
            unique.setdefault(normalized.casefold(), normalized)
    return [unique[key] for key in sorted(unique)]


def build_suggestion_items(titles: list[str]) -> list[ChatSuggestion]:
    return [
        {
            "title": f"Ask about {title}",
            "message": f"What are the key points in {title}?",
        }
        for title in dedupe_titles(titles)[:SUGGESTION_LIMIT]
    ]
