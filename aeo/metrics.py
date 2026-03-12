from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MetricsSummary:
    share_of_voice_target: float | None
    target_mention_rate: float
    competitor_mention_rate: float
    no_mentions_rate: float


def _safe_div(n: float, d: float) -> float | None:
    return (n / d) if d else None


def compute_share_of_voice_binary(
    *,
    target_domain: str,
    competitor_domains: list[str],
    detections_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute AEO metrics using per-response binary mentions.

    detections_rows should be a list of dict-like records containing at least:
    - response_id
    - brand_domain
    - mentioned_binary (0/1)
    - provider (optional)
    """

    # Group binary mentions by response_id
    by_response: dict[str, dict[str, int]] = {}
    for r in detections_rows:
        response_id = str(r["response_id"])
        brand = str(r["brand_domain"]).lower()
        mentioned = int(r["mentioned_binary"])
        by_response.setdefault(response_id, {})[brand] = max(
            mentioned, by_response.get(response_id, {}).get(brand, 0)
        )

    total_responses = len(by_response)
    if total_responses == 0:
        return {
            "total_responses": 0,
            "sov_target": None,
            "target_mention_rate": 0.0,
            "competitor_mention_rate": 0.0,
            "no_mentions_rate": 0.0,
        }

    target_key = target_domain.lower()
    competitor_keys = [d.lower() for d in competitor_domains]

    target_mentions = 0
    competitor_mentions_total = 0
    no_mentions = 0

    for _, brand_map in by_response.items():
        target_flag = int(brand_map.get(target_key, 0))
        competitor_flag = 1 if any(int(brand_map.get(k, 0)) for k in competitor_keys) else 0

        target_mentions += target_flag
        competitor_mentions_total += competitor_flag

        if not target_flag and not competitor_flag:
            no_mentions += 1

    sov = _safe_div(target_mentions, target_mentions + competitor_mentions_total)

    return {
        "total_responses": total_responses,
        "sov_target": sov,
        "target_mention_rate": target_mentions / total_responses,
        "competitor_mention_rate": competitor_mentions_total / total_responses,
        "no_mentions_rate": no_mentions / total_responses,
    }


def compute_visibility_by_provider(
    *,
    target_domain: str,
    competitor_domains: list[str],
    detections_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows_by_provider: dict[str, list[dict[str, Any]]] = {}
    for r in detections_rows:
        provider = str(r.get("provider", "unknown"))
        rows_by_provider.setdefault(provider, []).append(r)

    out: list[dict[str, Any]] = []
    for provider, rows in sorted(rows_by_provider.items()):
        metrics = compute_share_of_voice_binary(
            target_domain=target_domain,
            competitor_domains=competitor_domains,
            detections_rows=rows,
        )
        out.append({"provider": provider, **metrics})

    return out


def compute_average_rank(
    *,
    detections_rows: list[dict[str, Any]],
    brand_domains: list[str],
) -> list[dict[str, Any]]:
    # rank_position is only present for list-like answers
    stats: dict[str, list[int]] = {d.lower(): [] for d in brand_domains}

    for r in detections_rows:
        domain = str(r["brand_domain"]).lower()
        pos = r.get("rank_position")
        if pos is None:
            continue
        try:
            stats[domain].append(int(pos))
        except Exception:
            continue

    out: list[dict[str, Any]] = []
    for d in brand_domains:
        key = d.lower()
        positions = stats.get(key, [])
        avg = sum(positions) / len(positions) if positions else None
        out.append(
            {
                "brand_domain": d,
                "avg_rank_position": avg,
                "rank_observations": len(positions),
            }
        )
    return out
