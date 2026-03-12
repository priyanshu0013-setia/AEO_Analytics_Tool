from __future__ import annotations

import itertools
from dataclasses import dataclass


@dataclass(frozen=True)
class QueryVariant:
    seed: str
    text: str
    method: str  # template | rewrite


def generate_template_variants(seed: str) -> list[QueryVariant]:
    s = seed.strip()
    if not s:
        return []

    templates = [
        "{q}",
        "Best {q}",
        "Top {q}",
        "Recommended {q}",
        "{q} for international students",
        "Affordable {q}",
        "{q} near me",
        "Alternatives to {q}",
        "{q} comparison",
        "{q} reviews",
    ]

    variants: list[str] = []
    for t in templates:
        v = t.format(q=s)
        if v.lower() not in {x.lower() for x in variants}:
            variants.append(v)

    return [QueryVariant(seed=s, text=v, method="template") for v in variants]


def select_variants(variants: list[QueryVariant], max_count: int) -> list[QueryVariant]:
    max_count = max(1, min(10, int(max_count)))
    return list(itertools.islice(variants, 0, max_count))


def generate_variations(seed: str, count: int) -> list[QueryVariant]:
    """Generate query variations (prototype).

    For MVP we use deterministic templates only to keep costs low and runs reproducible.
    The architecture leaves room for LLM-based rewrites later.
    """

    base = generate_template_variants(seed)
    return select_variants(base, count)
