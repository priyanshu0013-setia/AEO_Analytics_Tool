from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class MentionDetection:
    brand_domain: str
    mentioned: bool
    mention_type: str  # domain | url
    matched_snippet: str | None
    rank_position: int | None


_LIST_ITEM_RE = re.compile(r"^\s*(?:\d+\.|\-|\*|•)\s+(?P<text>.+?)\s*$")


def _extract_list_items(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        m = _LIST_ITEM_RE.match(line)
        if m:
            item = (m.group("text") or "").strip()
            if item:
                items.append(item)
    return items


def _find_domain_snippet(haystack: str, needle: str, window: int = 80) -> str | None:
    if not needle:
        return None
    idx = haystack.lower().find(needle.lower())
    if idx < 0:
        return None
    start = max(0, idx - window)
    end = min(len(haystack), idx + len(needle) + window)
    snippet = haystack[start:end].strip()
    return snippet


def detect_mentions_and_rank(response_text: str | None, brand_domains: list[str]) -> list[MentionDetection]:
    if not response_text:
        return [
            MentionDetection(
                brand_domain=d,
                mentioned=False,
                mention_type="domain",
                matched_snippet=None,
                rank_position=None,
            )
            for d in brand_domains
        ]

    items = _extract_list_items(response_text)

    detections: list[MentionDetection] = []
    for d in brand_domains:
        snippet = _find_domain_snippet(response_text, d)
        mentioned = snippet is not None

        rank_pos: int | None = None
        if mentioned and items:
            for i, item in enumerate(items, start=1):
                if d.lower() in item.lower():
                    rank_pos = i
                    break

        detections.append(
            MentionDetection(
                brand_domain=d,
                mentioned=mentioned,
                mention_type="domain",
                matched_snippet=snippet,
                rank_position=rank_pos,
            )
        )

    return detections
