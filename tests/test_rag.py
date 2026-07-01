from azure_rag.rag import RetrievedChunk, build_messages


def test_build_messages_include_context_citations_and_question():
    messages = build_messages(
        "What does the support policy say?",
        [
            RetrievedChunk(
                title="support.md",
                chunk="Premium support replies within 4 business hours.",
                source_path="docs/support.md",
                score=2.1,
            )
        ],
    )

    assert messages[0]["role"] == "system"
    assert "grounded assistant" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "support.md" in messages[1]["content"]
    assert "Premium support replies within 4 business hours." in messages[1]["content"]
    assert "What does the support policy say?" in messages[1]["content"]
