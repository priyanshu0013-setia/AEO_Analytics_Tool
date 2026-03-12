"""Streamlit UI entrypoint for the Mini AEO Analytics Platform prototype."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict
from typing import Any

import pandas as pd
import streamlit as st

from aeo import (
    build_prompt,
    compute_average_rank,
    compute_share_of_voice_binary,
    compute_visibility_by_provider,
    detect_mentions_and_rank,
    generate_variations,
    normalize_and_resolve,
    redirect_chain_json,
)
from llm import LLMRequest
from llm.registry import available_clients
from reporting.report_builder import build_markdown_report
from storage import (
    APP_VERSION,
    PROMPT_VERSION,
    DetectionRecord,
    ResponseRecord,
    RunRecord,
    VariantRecord,
    connect,
    db_path,
    find_cached_response,
    init_db,
    insert_detections,
    insert_response,
    insert_run,
    insert_variants,
    list_run_detections,
    list_run_responses,
    list_runs,
    reports_out_dir,
    schema_path,
    utc_now_iso,
)


st.set_page_config(page_title="Mini AEO Analytics (Prototype)", layout="wide")


def _parse_comma_separated(s: str) -> list[str]:
    parts = [p.strip() for p in (s or "").split(",")]
    return [p for p in parts if p]


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _as_dict_rows(rows: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        try:
            out.append(dict(r))
        except Exception:
            out.append({k: getattr(r, k) for k in dir(r) if not k.startswith("_")})
    return out


st.title("Mini AEO Analytics Platform (Prototype)")
st.caption(
    "Measure brand visibility in LLM answers vs competitors. "
    "Prototype-focused: clear methodology + reproducible run artifacts."
)


# DB init
conn = connect(db_path())
init_db(conn, schema_path())


tab_run, tab_history = st.tabs(["Run", "History"])


with tab_run:
    st.subheader("Inputs")
    col_a, col_b = st.columns([2, 2])

    with col_a:
        target_input = st.text_input(
            "Target domain or landing page URL",
            value="ascendnow.org",
            placeholder="https://ascendnow.org or https://example.com/some-page",
        )
        competitor_input = st.text_input(
            "Competitor domains/URLs (comma-separated)",
            value="crimsoneducation.org, collegeadvisor.com",
        )
        seed_queries_text = st.text_area(
            "Seed queries (one per line)",
            value=(
                "Best college admissions counselors\n"
                "Ivy League admission help\n"
                "IB tutoring services\n"
            ),
            height=120,
        )

    with col_b:
        st.markdown("**LLM Providers (enabled only when secrets exist)**")
        clients = available_clients()
        configured = [c for c in clients if c.is_configured()]

        if not configured:
            st.warning(
                "No API keys found in Streamlit secrets. Add at least GEMINI_API_KEY (or OPENAI_API_KEY / ANTHROPIC_API_KEY)."
            )

        provider_options = [c.provider for c in configured]
        selected_providers = st.multiselect(
            "Providers to run",
            options=provider_options,
            default=provider_options[:1] if provider_options else [],
        )

        variations_per_query = st.slider("Variations per seed query", 5, 10, 5)
        temperature = st.number_input("Temperature", min_value=0.0, max_value=1.5, value=0.0, step=0.1)
        max_output_tokens = st.number_input("Max output tokens", min_value=128, max_value=2048, value=600, step=64)
        resolve_redirects = st.checkbox("Resolve redirects (record final URL)", value=True)
        use_cache = st.checkbox("Use cache (reuse exact prompt outputs)", value=True)

    st.divider()
    st.subheader("Run")

    run_clicked = st.button("Run analysis", type="primary", disabled=not (target_input and seed_queries_text and selected_providers))

    if run_clicked:
        run_id = str(uuid.uuid4())
        created_at = utc_now_iso()

        seed_queries = [q.strip() for q in seed_queries_text.splitlines() if q.strip()]
        competitors_raw_list = _parse_comma_separated(competitor_input)

        st.write("Normalizing URLs…")
        target_norm = normalize_and_resolve(target_input, resolve=resolve_redirects)
        competitor_norms = [normalize_and_resolve(c, resolve=resolve_redirects) for c in competitors_raw_list]
        competitor_domains = [c.registrable_domain for c in competitor_norms if c.registrable_domain]

        brand_domains = [d for d in [target_norm.registrable_domain] + competitor_domains if d]

        settings = {
            "providers": selected_providers,
            "variations_per_query": variations_per_query,
            "temperature": float(temperature),
            "max_output_tokens": int(max_output_tokens),
            "resolve_redirects": bool(resolve_redirects),
            "use_cache": bool(use_cache),
        }

        run_record = RunRecord(
            run_id=run_id,
            created_at=created_at,
            app_version=APP_VERSION,
            prompt_version=PROMPT_VERSION,
            target_input_raw=target_norm.input_raw,
            target_input_normalized=target_norm.input_normalized,
            target_final_url=target_norm.final_url,
            target_registrable_domain=target_norm.registrable_domain,
            target_redirect_chain_json=redirect_chain_json(target_norm.redirect_chain),
            competitors_input_raw=competitor_input,
            settings_json=json.dumps(settings, ensure_ascii=False),
        )
        insert_run(conn, run_record)

        # Variants
        st.write("Generating query variations…")
        variants: list[VariantRecord] = []
        for seed in seed_queries:
            qs = generate_variations(seed, variations_per_query)
            for qv in qs:
                variants.append(
                    VariantRecord(
                        variant_id=str(uuid.uuid4()),
                        run_id=run_id,
                        seed_query=qv.seed,
                        variant_text=qv.text,
                        variant_method=qv.method,
                        created_at=created_at,
                    )
                )
        insert_variants(conn, variants)

        # Provider map
        client_by_provider = {c.provider: c for c in configured}
        chosen_clients = [client_by_provider[p] for p in selected_providers if p in client_by_provider]

        st.write("Querying providers…")
        total_calls = len(variants) * len(chosen_clients)
        progress = st.progress(0)
        call_idx = 0

        for v in variants:
            prompt = build_prompt(v.variant_text)
            prompt_hash = _sha256(prompt)
            request_params = {
                "temperature": float(temperature),
                "max_output_tokens": int(max_output_tokens),
            }

            for client in chosen_clients:
                call_idx += 1
                progress.progress(min(1.0, call_idx / max(1, total_calls)))

                model_id = client.default_model()

                # Cache lookup
                cached_row = None
                if use_cache:
                    cached_row = find_cached_response(
                        conn,
                        provider=client.provider,
                        model_id=model_id,
                        prompt_hash=prompt_hash,
                        request_params=request_params,
                    )

                if cached_row is not None:
                    response_id = str(uuid.uuid4())
                    insert_response(
                        conn,
                        ResponseRecord(
                            response_id=response_id,
                            run_id=run_id,
                            variant_id=v.variant_id,
                            provider=client.provider,
                            model_id=model_id,
                            model_version=cached_row["model_version"],
                            request_params_json=cached_row["request_params_json"],
                            status="cached",
                            error_message=None,
                            response_text=cached_row["response_text"],
                            response_raw_json=cached_row["response_raw_json"],
                            latency_ms=cached_row["latency_ms"],
                            created_at=utc_now_iso(),
                        ),
                    )

                    detections = detect_mentions_and_rank(cached_row["response_text"], brand_domains)
                    det_records = [
                        DetectionRecord(
                            detection_id=str(uuid.uuid4()),
                            response_id=response_id,
                            brand_domain=d.brand_domain,
                            mentioned_binary=1 if d.mentioned else 0,
                            mention_type=d.mention_type,
                            matched_snippet=d.matched_snippet,
                            rank_position=d.rank_position,
                            created_at=utc_now_iso(),
                        )
                        for d in detections
                    ]
                    insert_detections(conn, det_records)
                    continue

                req = LLMRequest(
                    prompt=prompt,
                    temperature=float(temperature),
                    max_output_tokens=int(max_output_tokens),
                )
                result = client.generate(req, model=model_id)

                response_id = str(uuid.uuid4())
                raw_payload = {
                    "prompt_hash": prompt_hash,
                    "provider_raw": result.raw,
                }
                insert_response(
                    conn,
                    ResponseRecord(
                        response_id=response_id,
                        run_id=run_id,
                        variant_id=v.variant_id,
                        provider=result.provider,
                        model_id=result.model_id,
                        model_version=result.model_version,
                        request_params_json=json.dumps(request_params, sort_keys=True),
                        status=result.status,
                        error_message=result.error_message,
                        response_text=result.text,
                        response_raw_json=json.dumps(raw_payload, ensure_ascii=False),
                        latency_ms=result.latency_ms,
                        created_at=utc_now_iso(),
                    ),
                )

                detections = detect_mentions_and_rank(result.text, brand_domains)
                det_records = [
                    DetectionRecord(
                        detection_id=str(uuid.uuid4()),
                        response_id=response_id,
                        brand_domain=d.brand_domain,
                        mentioned_binary=1 if d.mentioned else 0,
                        mention_type=d.mention_type,
                        matched_snippet=d.matched_snippet,
                        rank_position=d.rank_position,
                        created_at=utc_now_iso(),
                    )
                    for d in detections
                ]
                insert_detections(conn, det_records)

        st.success(f"Run complete: {run_id}")

        # Load & compute metrics
        responses_rows = _as_dict_rows(list_run_responses(conn, run_id))
        det_rows = _as_dict_rows(list_run_detections(conn, run_id))

        summary = compute_share_of_voice_binary(
            target_domain=target_norm.registrable_domain,
            competitor_domains=competitor_domains,
            detections_rows=det_rows,
        )
        by_provider = compute_visibility_by_provider(
            target_domain=target_norm.registrable_domain,
            competitor_domains=competitor_domains,
            detections_rows=det_rows,
        )
        avg_rank = compute_average_rank(detections_rows=det_rows, brand_domains=brand_domains)

        st.subheader("Summary")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total responses", int(summary.get("total_responses", 0)))
        col2.metric("SoV (target)", f"{(summary.get('sov_target') or 0) * 100:.1f}%" if summary.get("sov_target") is not None else "N/A")
        col3.metric("Target mention rate", f"{summary.get('target_mention_rate', 0) * 100:.1f}%")
        col4.metric("No-mentions rate", f"{summary.get('no_mentions_rate', 0) * 100:.1f}%")

        st.markdown("**Visibility by provider**")
        st.dataframe(pd.DataFrame(by_provider), use_container_width=True)

        st.markdown("**Average rank (only when list-like)**")
        st.dataframe(pd.DataFrame(avg_rank), use_container_width=True)

        st.divider()
        st.subheader("Raw Responses")
        df_resp = pd.DataFrame(responses_rows)
        if not df_resp.empty:
            st.dataframe(
                df_resp[["response_id", "provider", "model_id", "status", "seed_query", "variant_text", "latency_ms", "created_at"]],
                use_container_width=True,
                height=280,
            )
            response_pick = st.selectbox("Inspect response", options=[""] + df_resp["response_id"].tolist())
            if response_pick:
                row = df_resp[df_resp["response_id"] == response_pick].iloc[0].to_dict()
                st.markdown(f"**Provider:** {row.get('provider')} | **Model:** {row.get('model_id')} | **Status:** {row.get('status')}")
                st.markdown(f"**Seed:** {row.get('seed_query')}")
                st.markdown(f"**Variant:** {row.get('variant_text')}")
                st.text_area("Response text", value=row.get("response_text") or "", height=240)
                st.text_area("Raw JSON payload (stored)", value=row.get("response_raw_json") or "", height=180)

        st.divider()
        st.subheader("Export report")
        run_dict = asdict(run_record)
        artifacts = build_markdown_report(
            out_dir=reports_out_dir(),
            run=run_dict,
            summary=summary,
            by_provider=by_provider,
            avg_rank=avg_rank,
            responses_rows=responses_rows,
            detections_rows=det_rows,
        )

        st.write("Generated:")
        st.write(str(artifacts.markdown_path))

        st.download_button(
            "Download report (Markdown)",
            data=artifacts.markdown_path.read_text(encoding="utf-8"),
            file_name=artifacts.markdown_path.name,
            mime="text/markdown",
        )
        st.download_button(
            "Download responses (CSV)",
            data=artifacts.responses_csv_path.read_text(encoding="utf-8"),
            file_name=artifacts.responses_csv_path.name,
            mime="text/csv",
        )
        st.download_button(
            "Download detections (CSV)",
            data=artifacts.detections_csv_path.read_text(encoding="utf-8"),
            file_name=artifacts.detections_csv_path.name,
            mime="text/csv",
        )


with tab_history:
    st.subheader("Recent runs")
    runs = _as_dict_rows(list_runs(conn, limit=50))
    if not runs:
        st.info("No runs yet. Use the Run tab to execute an analysis.")
    else:
        df_runs = pd.DataFrame(runs)
        st.dataframe(
            df_runs[["run_id", "created_at", "target_registrable_domain", "competitors_input_raw", "settings_json"]],
            use_container_width=True,
            height=260,
        )
        selected_run = st.selectbox("Open a run", options=[""] + df_runs["run_id"].tolist())
        if selected_run:
            resp_rows = _as_dict_rows(list_run_responses(conn, selected_run))
            det_rows = _as_dict_rows(list_run_detections(conn, selected_run))
            st.markdown("**Responses**")
            st.dataframe(pd.DataFrame(resp_rows), use_container_width=True, height=240)
            st.markdown("**Detections**")
            st.dataframe(pd.DataFrame(det_rows), use_container_width=True, height=240)
