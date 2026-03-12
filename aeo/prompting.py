from __future__ import annotations


def build_prompt(query: str) -> str:
    """Prompt template (prototype).

    Intentionally simple and consistent across providers.
    Encourages list-style answers to enable rank extraction when applicable.
    """

    q = query.strip()
    return (
        "You are helping a user choose between services/websites. "
        "Answer the question with a concise, neutral recommendation list when possible. "
        "When you mention an organization, include its website domain if you know it.\n\n"
        f"Question: {q}\n"
    )
