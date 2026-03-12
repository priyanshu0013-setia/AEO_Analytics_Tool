from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    created_at: str
    app_version: str
    prompt_version: str
    target_input_raw: str
    target_input_normalized: str
    target_final_url: str | None
    target_registrable_domain: str
    target_redirect_chain_json: str | None
    competitors_input_raw: str
    settings_json: str


@dataclass(frozen=True)
class VariantRecord:
    variant_id: str
    run_id: str
    seed_query: str
    variant_text: str
    variant_method: str
    created_at: str


@dataclass(frozen=True)
class ResponseRecord:
    response_id: str
    run_id: str
    variant_id: str
    provider: str
    model_id: str
    model_version: str | None
    request_params_json: str
    status: str
    error_message: str | None
    response_text: str | None
    response_raw_json: str | None
    latency_ms: int | None
    created_at: str


@dataclass(frozen=True)
class DetectionRecord:
    detection_id: str
    response_id: str
    brand_domain: str
    mentioned_binary: int
    mention_type: str
    matched_snippet: str | None
    rank_position: int | None
    created_at: str


def insert_run(conn: sqlite3.Connection, record: RunRecord) -> None:
    conn.execute(
        """
        INSERT INTO runs(
          run_id, created_at, app_version, prompt_version,
          target_input_raw, target_input_normalized, target_final_url,
          target_registrable_domain, target_redirect_chain_json,
          competitors_input_raw, settings_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.run_id,
            record.created_at,
            record.app_version,
            record.prompt_version,
            record.target_input_raw,
            record.target_input_normalized,
            record.target_final_url,
            record.target_registrable_domain,
            record.target_redirect_chain_json,
            record.competitors_input_raw,
            record.settings_json,
        ),
    )
    conn.commit()


def insert_variants(conn: sqlite3.Connection, variants: Iterable[VariantRecord]) -> None:
    conn.executemany(
        """
        INSERT INTO query_variants(
          variant_id, run_id, seed_query, variant_text, variant_method, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                v.variant_id,
                v.run_id,
                v.seed_query,
                v.variant_text,
                v.variant_method,
                v.created_at,
            )
            for v in variants
        ],
    )
    conn.commit()


def insert_response(conn: sqlite3.Connection, record: ResponseRecord) -> None:
    conn.execute(
        """
        INSERT INTO llm_responses(
          response_id, run_id, variant_id,
          provider, model_id, model_version,
          request_params_json, status, error_message,
          response_text, response_raw_json,
          latency_ms, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.response_id,
            record.run_id,
            record.variant_id,
            record.provider,
            record.model_id,
            record.model_version,
            record.request_params_json,
            record.status,
            record.error_message,
            record.response_text,
            record.response_raw_json,
            record.latency_ms,
            record.created_at,
        ),
    )
    conn.commit()


def insert_detections(conn: sqlite3.Connection, detections: Iterable[DetectionRecord]) -> None:
    conn.executemany(
        """
        INSERT INTO detections(
          detection_id, response_id, brand_domain, mentioned_binary,
          mention_type, matched_snippet, rank_position, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                d.detection_id,
                d.response_id,
                d.brand_domain,
                d.mentioned_binary,
                d.mention_type,
                d.matched_snippet,
                d.rank_position,
                d.created_at,
            )
            for d in detections
        ],
    )
    conn.commit()


def find_cached_response(
    conn: sqlite3.Connection,
    *,
    provider: str,
    model_id: str,
    prompt_hash: str,
    request_params: dict[str, Any],
) -> sqlite3.Row | None:
    params_json = json.dumps(request_params, sort_keys=True)
    row = conn.execute(
        """
        SELECT * FROM llm_responses
        WHERE provider = ?
          AND model_id = ?
          AND request_params_json = ?
          AND response_raw_json IS NOT NULL
          AND response_raw_json LIKE ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (provider, model_id, params_json, f"%\"prompt_hash\": \"{prompt_hash}\"%"),
    ).fetchone()
    return row


def list_runs(conn: sqlite3.Connection, limit: int = 50) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()


def list_run_responses(conn: sqlite3.Connection, run_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT r.*, q.seed_query, q.variant_text
        FROM llm_responses r
        JOIN query_variants q ON q.variant_id = r.variant_id
        WHERE r.run_id = ?
        ORDER BY r.created_at ASC
        """,
        (run_id,),
    ).fetchall()


def list_run_detections(conn: sqlite3.Connection, run_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT d.*, r.provider, r.model_id, r.variant_id
        FROM detections d
        JOIN llm_responses r ON r.response_id = d.response_id
        WHERE r.run_id = ?
        ORDER BY d.created_at ASC
        """,
        (run_id,),
    ).fetchall()
