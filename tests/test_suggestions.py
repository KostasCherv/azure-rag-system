from azure_rag.suggestions import build_suggestion_items, dedupe_titles


def test_dedupe_titles_normalizes_deduplicates_and_sorts() -> None:
    assert dedupe_titles(
        ["  Zebra   Guide ", "", "alpha manual", "ALPHA MANUAL", "   "]
    ) == ["alpha manual", "Zebra Guide"]


def test_build_suggestion_items_caps_and_formats_titles() -> None:
    assert build_suggestion_items(["A", "B", "C", "D", "E"]) == [
        {"title": "Ask about A", "message": "What are the key points in A?"},
        {"title": "Ask about B", "message": "What are the key points in B?"},
        {"title": "Ask about C", "message": "What are the key points in C?"},
        {"title": "Ask about D", "message": "What are the key points in D?"},
    ]
