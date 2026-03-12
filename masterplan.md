# Mini AEO Analytics Platform — Prototype Masterplan

## 1) Overview
A small prototype that measures how often a target brand appears in AI-generated answers compared to competitors. It simulates “answer engine” behavior by sending query variations to multiple LLMs (Gemini, GPT, Claude), collecting responses, detecting brand mentions, and producing visibility metrics (Share of Voice, rank position when answers are lists, and visibility by provider/model).

This is intentionally evaluator-friendly: it prioritizes clarity of methodology, automation, and reproducibility over a large feature set.

## 2) Objectives
- Demonstrate AEO measurement concepts: presence, competitive comparison, and rank in answer lists.
- Demonstrate automation: query generation, multi-provider LLM calls, persistence, and reporting.
- Demonstrate analytical thinking: transparent detection rules and well-defined metrics.
- Produce a sample report using the assignment’s example inputs.

## 3) Scope & Non-goals
### In scope
- Streamlit UI for inputs, running analyses, and exporting results.
- Generate 5–10 variations per seed query.
- Query multiple providers (Gemini/GPT/Claude) if their keys exist in Streamlit secrets.
- Persist runs and raw responses in SQLite with timestamps and metadata.
- Detect brand mentions using domains (high precision) and compute AEO metrics.
- Export an evaluator-ready report with excerpts and links to raw responses.

### Non-goals
- Not production-grade (no auth/multi-tenant, no heavy infra).
- Not guaranteed deterministic outputs; reproducibility is via stored artifacts.

## 4) Inputs & UX
### Inputs
- Target: domain or landing page URL.
- Competitors: comma-separated domains/URLs.
- Seed queries: one per line.
- Settings: variations per query (5–10), temperature (default 0), caching on/off.

### API keys (Streamlit secrets only)
Providers are enabled only when these secrets exist:
- `GEMINI_API_KEY`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`

Keys are never written to SQLite and never logged.

## 5) Methodology
### URL normalization
- Accept domain or URL; assume `https://` if scheme missing.
- Normalize host and strip fragments.
- Resolve redirects; store redirect chain and final URL.
- Extract registrable domain (eTLD+1) for detection.

### Query generation
- Hybrid approach: deterministic templates + optional rewrite-style variants.
- Store every variant with method label (template vs rewrite) for auditability.

### Brand detection
- Primary: per-response binary mention based on registrable domain presence.
- Rank position: only when list-like structure can be confidently extracted.

## 6) Metrics
- Share of Voice (primary): computed from per-response binary mentions.
- Average rank position: computed only when list ranks are detected.
- Visibility by provider/model.
- No-mentions rate.

## 7) Reproducibility & audit trail
- Each run has a `run_id`.
- Persist: normalized inputs, variants, provider/model identifiers, request params, timestamps, raw JSON outputs, and cached-vs-fresh flags.
- Ensure any metric can be traced to specific responses.

## 8) Deliverables
- Working Streamlit prototype.
- Short documentation (README + this plan).
- Sample report using example inputs.

## 9) Example inputs
Target: `ascendnow.org`
Competitors: `crimsoneducation.org`, `collegeadvisor.com`
Queries:
- Best college admissions counselors
- Ivy League admission help
- IB tutoring services
