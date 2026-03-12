from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse, urlunparse

import requests
import tldextract


@dataclass(frozen=True)
class NormalizedUrl:
    input_raw: str
    input_normalized: str
    final_url: str | None
    redirect_chain: list[dict[str, Any]]
    registrable_domain: str


_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


def _ensure_url(s: str) -> str:
    s = s.strip()
    if not s:
        return s
    if _SCHEME_RE.match(s):
        return s
    return "https://" + s


def normalize_input_url(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return raw

    url = _ensure_url(raw)
    parsed = urlparse(url)

    scheme = (parsed.scheme or "https").lower()
    netloc = (parsed.netloc or "").strip().lower().rstrip(".")

    # Strip fragment for canonical identity.
    fragment = ""

    # Keep path/query as provided; callers can choose whether to drop tracking later.
    normalized = urlunparse(
        (scheme, netloc, parsed.path or "", parsed.params or "", parsed.query or "", fragment)
    )
    return normalized


def registrable_domain_from_url(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    ext = tldextract.extract(host)
    if not ext.suffix:
        # e.g., localhost or invalid domain
        return host
    return f"{ext.domain}.{ext.suffix}".lower()


def resolve_redirects(url: str, timeout_s: float = 12.0) -> tuple[str | None, list[dict[str, Any]]]:
    chain: list[dict[str, Any]] = []
    try:
        resp = requests.get(url, allow_redirects=True, timeout=timeout_s, headers={"User-Agent": "aeo-prototype/0.1"})
        for h in resp.history:
            chain.append({"status": h.status_code, "url": h.url})
        chain.append({"status": resp.status_code, "url": resp.url})
        return resp.url, chain
    except Exception as e:  # noqa: BLE001
        chain.append({"error": str(e), "url": url})
        return None, chain


def normalize_and_resolve(raw: str, *, resolve: bool = True) -> NormalizedUrl:
    normalized = normalize_input_url(raw)
    final_url: str | None = None
    chain: list[dict[str, Any]] = []
    if normalized and resolve:
        final_url, chain = resolve_redirects(normalized)

    effective_for_domain = final_url or normalized
    domain = registrable_domain_from_url(effective_for_domain) if effective_for_domain else ""

    return NormalizedUrl(
        input_raw=raw,
        input_normalized=normalized,
        final_url=final_url,
        redirect_chain=chain,
        registrable_domain=domain,
    )


def redirect_chain_json(chain: list[dict[str, Any]]) -> str | None:
    if not chain:
        return None
    return json.dumps(chain, ensure_ascii=False)
