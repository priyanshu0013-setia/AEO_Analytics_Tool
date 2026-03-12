# Mini AEO Analytics Platform (Prototype) — Technical Specification

This document is the *source of truth* for how the prototype behaves and how the codebase works today.

It is intentionally concrete: it specifies inputs/outputs, storage schema, algorithms, and the execution flow. Where the master plan describes intent, this spec describes the actual operational behavior implemented in the repository.

## 1) Goals and non-goals

### Goals
- Provide an evaluator-friendly prototype that measures brand visibility in LLM answers relative to competitors.
- Make runs reproducible via stored artifacts (inputs, prompt, request params, raw LLM payloads, detections).
- Keep methodology transparent (domain-based mention detection + simple list rank extraction).

### Non-goals
- Not production-grade (no auth, no multi-tenant isolation, no background job orchestration).
- No guarantee of deterministic LLM outputs; reproducibility is achieved by storing artifacts.
- No semantic/NER brand matching; detection is domain substring matching only.

## 2) Repository structure and responsibilities

### UI
- `app/streamlit_app.py`
  - Streamlit UI entrypoint.
  - Orchestrates the full run: normalize URLs → generate variants → prompt → call providers (or cache) → store → detect → compute metrics → render tables → export report.

### Core AEO logic
- `aeo/url_normalization.py`
  - Normalizes user-entered domains/URLs.
  - Optional redirect resolution.
  - Extracts registrable domain using `tldextract`.

- `aeo/query_generation.py`
  - Generates deterministic template variations (no LLM rewrite step in current implementation).

- `aeo/prompting.py`
  - Builds the prompt template used for all providers.

- `aeo/detection.py`
  - Detects domain mentions via substring search.
  - Extracts list items using a simple per-line regex and assigns list rank positions if possible.

- `aeo/metrics.py`
  - Computes Share of Voice (binary mention SoV), mention rates, no-mentions rate.
  - Computes visibility by provider.
  - Computes average rank position (only when rank is detected).

### LLM provider adapters
- `llm/types.py`
  - Data structures: `LLMRequest`, `LLMResult`.

- `llm/providers.py`
  - Provider protocol definition.

- `llm/registry.py`
  - Registry for available provider clients.

- `llm/gemini_client.py`
  - Google Gemini adapter (via `google-genai`).

- `llm/openai_client.py`
  - OpenAI adapter (via `openai`).

- `llm/anthropic_client.py`
  - Anthropic adapter (via `anthropic`).

### Persistence
- `storage/schema.sql`
  - SQLite schema used for all run artifacts.

- `storage/db.py`
  - Opens SQLite and initializes schema.

- `storage/store.py`
  - Inserts and queries artifacts.
  - Implements caching lookup.

- `storage/paths.py`
  - Defines where DB and report outputs are stored.

- `storage/constants.py`
  - App and prompt version strings stored on each run.

### Reporting
- `reporting/report_builder.py`
  - Exports run artifacts to Markdown and CSV.

## 3) Configuration (secrets)

The app reads API keys from Streamlit secrets only (never from environment variables in current implementation).

Required secrets to enable providers:
- `GEMINI_API_KEY` → enables provider `gemini`
- `OPENAI_API_KEY` → enables provider `openai`
- `ANTHROPIC_API_KEY` → enables provider `anthropic`

Notes:
- If a key is missing, the provider is hidden/disabled in the UI.
- Keys are never written to SQLite and are never logged intentionally.

## 4) Filesystem paths and artifacts

All storage is local and workspace-relative.

- SQLite DB file:
  - `data/aeo_runs.sqlite3`

- Report outputs:
  - `reports/out/`
  - Contains per-run:
    - `report_<run_id>.md`
    - `responses_<run_id>.csv`
    - `detections_<run_id>.csv`

## 5) End-to-end runtime flow

The following steps occur when a user clicks **Run analysis** in the Streamlit UI.

### 5.1 Inputs
UI inputs:
- Target domain or landing page URL (string)
- Competitors (comma-separated string)
- Seed queries (one per line)
- Providers selected (subset of enabled providers)
- Variations per query (`5`–`10`)
- Temperature (`0.0`–`1.5`)
- Max output tokens (`128`–`2048`)
- Resolve redirects (boolean)
- Use cache (boolean)

### 5.2 Create run_id
- A new run UUID is generated (`run_id`).
- Run timestamp is recorded as UTC ISO-8601.

### 5.3 Normalize target + competitor URLs
Implementation (`aeo/url_normalization.py`):

1) **Ensure URL scheme**
- If the input does not start with a scheme like `http://` or `https://`, the app prepends `https://`.

2) **Normalize**
- Scheme is lowercased.
- Host/netloc is lowercased and trailing dot is removed.
- Fragment (`#...`) is removed.
- Path and query are preserved.

3) **Optional redirect resolution** (if `resolve_redirects = True`)
- Uses `requests.get(..., allow_redirects=True, timeout=12)` with `User-Agent: aeo-prototype/0.1`.
- Stores redirect history (status + url) plus final response (status + url).
- If redirect resolution fails, stores an error entry and proceeds.

4) **Registrable domain extraction**
- Uses `tldextract` on the effective URL host.
- If a TLD suffix cannot be determined, returns the host as-is.
- Example: `https://www.example.co.uk/foo` → `example.co.uk`.

Outputs persisted to the `runs` table:
- `target_input_raw`
- `target_input_normalized`
- `target_final_url` (nullable)
- `target_redirect_chain_json` (nullable)
- `target_registrable_domain`
- `competitors_input_raw`

### 5.4 Generate query variants
Implementation (`aeo/query_generation.py`):

- Variants are deterministic templates only.
- The system generates a fixed template list and dedupes case-insensitively.
- It then selects the first `N` variants (where `N` is variations-per-query clamped to `1..10`).

Template set:
- `{q}`
- `Best {q}`
- `Top {q}`
- `Recommended {q}`
- `{q} for international students`
- `Affordable {q}`
- `{q} near me`
- `Alternatives to {q}`
- `{q} comparison`
- `{q} reviews`

Each generated variant is stored in `query_variants` with:
- `variant_method = "template"`
- `seed_query`
- `variant_text`

### 5.5 Build prompt
Implementation (`aeo/prompting.py`):

For each `variant_text`, the prompt is built as:

- System instruction text (single string) encouraging:
  - concise, neutral recommendation list
  - inclusion of organization website domain when known
- Then the question line: `Question: <variant_text>`

A `prompt_hash` is computed as SHA-256 of the exact prompt string.

### 5.6 LLM request parameters
For each provider call, request params are:
- `temperature`: float from UI
- `max_output_tokens`: int from UI

These are stored as JSON in `llm_responses.request_params_json` using **sorted keys**, e.g.:

```json
{"max_output_tokens": 600, "temperature": 0.0}
```

### 5.7 Cache lookup (optional)
If `use_cache = True`, the app attempts to reuse a previous response.

Implementation (`storage/store.py::find_cached_response`):

A cached row is eligible if all are true:
- `provider` matches
- `model_id` matches
- `request_params_json` matches exactly (string equality)
- `response_raw_json IS NOT NULL`
- `response_raw_json` contains the substring `"prompt_hash": "<prompt_hash>"`

If multiple matches exist, it selects the most recent (`ORDER BY created_at DESC LIMIT 1`).

If a cached row is used:
- A new `response_id` is generated.
- A new `llm_responses` record is inserted with:
  - `status = "cached"`
  - `response_text` copied from cached row
  - `response_raw_json` copied from cached row
  - `latency_ms` copied from cached row

This preserves traceability: the current run records that it reused an earlier artifact.

### 5.8 Provider execution
Provider adapters return an `LLMResult` with:
- `status`: `ok | blocked | error`
- `text`: extracted answer (nullable)
- `raw`: provider SDK raw payload (nullable)
- `latency_ms`: measured around the SDK call (nullable on failure)

The following provider defaults are used unless changed in code:

#### OpenAI (`llm/openai_client.py`)
- Provider key: `openai`
- Default model: `gpt-4o-mini`
- API used: `client.chat.completions.create(...)`

Text extraction:
- `resp.choices[0].message.content` (if present)

Raw payload:
- `resp.model_dump()`

Status mapping:
- `ok` on successful call
- `error` on exception

#### Gemini (`llm/gemini_client.py`)
- Provider key: `gemini`
- Default model: `gemini-1.5-flash`
- API used: `genai.Client(...).models.generate_content(...)`

Text extraction:
- `resp.text` (best effort)

Raw payload:
- `resp.model_dump()` if available else `resp.to_dict()` else `{"repr": ...}`

Status mapping:
- If `text` is empty and raw indicates `promptFeedback.blockReason`, sets `blocked`
- Otherwise `ok`

#### Anthropic (`llm/anthropic_client.py`)
- Provider key: `anthropic`
- Default model: `claude-3-5-sonnet-20240620`
- API used: `client.messages.create(...)`

Text extraction:
- Concatenates `resp.content` blocks of type `text`.

Raw payload:
- `resp.model_dump()` if available else `{"repr": ...}`

Status mapping:
- `ok` on successful call
- `error` on exception

### 5.9 Persist LLM response
For a non-cached provider call, the app persists a row in `llm_responses`:

- `response_raw_json` is a JSON string that wraps provider payload along with the `prompt_hash`:

```json
{
  "prompt_hash": "<sha256 of full prompt>",
  "provider_raw": { ... provider SDK dump ... }
}
```

- `status` is written from `LLMResult.status`.
- `error_message` is written if status is `error`.

### 5.10 Mention detection + rank extraction
Implementation (`aeo/detection.py::detect_mentions_and_rank`):

Inputs:
- `response_text`: LLM answer string (nullable)
- `brand_domains`: list of registrable domains including:
  - target domain
  - all competitor registrable domains

Outputs:
- A `MentionDetection` record per brand domain.

Mention detection rule (binary):
- `mentioned = True` iff the brand domain appears as a substring in the full response text (case-insensitive).

Matched snippet:
- If mentioned, stores up to an ~80 character context window around the first occurrence.

List extraction (for ranking):
- Parses response line-by-line.
- Lines matching the regex are treated as list items:
  - numbered: `1.` `2.` etc.
  - bullets: `-` `*` `•`

Rank position rule:
- If list items were extracted and a brand domain is mentioned anywhere in the response:
  - Find the first list item containing the domain substring.
  - Assign its 1-based index as `rank_position`.
- If no list items are extracted (or the domain isn’t inside any item), `rank_position = NULL`.

Persistence:
- Each detection is inserted into `detections` with:
  - `mentioned_binary` as `0/1`
  - `mention_type = "domain"` (current implementation)
  - `matched_snippet` (nullable)
  - `rank_position` (nullable)

### 5.11 Metrics computation
Metrics are computed after the run completes by loading all responses and detections for the run.

#### 5.11.1 Share of Voice (binary)
Implementation (`aeo/metrics.py::compute_share_of_voice_binary`):

The detections are grouped by `response_id`.

For each response:
- `target_flag = 1` if the target domain has `mentioned_binary = 1`, else `0`.
- `competitor_flag = 1` if **any** competitor domain has `mentioned_binary = 1`, else `0`.
- `no_mentions_flag = 1` if `target_flag == 0` and `competitor_flag == 0`.

Aggregates across all responses:
- `target_mentions = Σ target_flag`
- `competitor_mentions_total = Σ competitor_flag`
- `no_mentions = Σ no_mentions_flag`
- `total_responses = number of unique response_id`

Outputs:
- `target_mention_rate = target_mentions / total_responses`
- `competitor_mention_rate = competitor_mentions_total / total_responses`
- `no_mentions_rate = no_mentions / total_responses`

Share of Voice (target):

- If `(target_mentions + competitor_mentions_total) > 0`:

$$\text{SoV}_{target} = \frac{target\_mentions}{target\_mentions + competitor\_mentions\_total}$$

- Else SoV is `N/A` (stored as `null`).

#### 5.11.2 Visibility by provider
Implementation (`aeo/metrics.py::compute_visibility_by_provider`):

- Groups detection rows by `provider`.
- Computes the same binary metrics per provider group.

#### 5.11.3 Average rank position
Implementation (`aeo/metrics.py::compute_average_rank`):

- For each brand domain, collect all `rank_position` values that are not null.
- Compute:

$$\text{avg\_rank} = \frac{\sum rank\_position}{\#(rank\_position)}$$

- If a brand has no rank observations, `avg_rank_position = N/A`.

## 6) Reporting and exports

Implementation (`reporting/report_builder.py::build_markdown_report`).

When a run completes, the app generates:
- Responses CSV: `responses_<run_id>.csv`
- Detections CSV: `detections_<run_id>.csv`
- Markdown report: `report_<run_id>.md`

### 6.1 Responses CSV
Columns written:
- `response_id`
- `run_id`
- `provider`
- `model_id`
- `status`
- `seed_query`
- `variant_text`
- `created_at`
- `latency_ms`

### 6.2 Detections CSV
Columns written:
- `response_id`
- `brand_domain`
- `mentioned_binary`
- `rank_position`
- `matched_snippet`
- `provider`

### 6.3 Markdown report
Sections:
- Header (Run ID, generated timestamp, target, competitors)
- Summary (responses, SoV, mention rates)
- Visibility by provider (table)
- Average rank (table)
- Evidence excerpts (up to 10)
- Reproducibility notes

Evidence selection:
- Prefers responses where the target is mentioned.
- Excerpts are whitespace-collapsed and truncated to a configurable character limit.

Important note:
- The report does not embed full raw payloads; it references response IDs so the user can inspect full artifacts in the app.

## 7) SQLite schema (authoritative)

The schema is defined in `storage/schema.sql` and initialized on app startup.

### 7.1 Table: runs
Primary key: `run_id`.

Stores:
- App versions
- Normalized inputs
- Target redirect chain
- Competitor raw string
- Settings JSON

### 7.2 Table: query_variants
Primary key: `variant_id`.
Foreign key: `run_id` → `runs(run_id)`.

Stores:
- `seed_query`
- `variant_text`
- `variant_method` (currently always `template`)

### 7.3 Table: llm_responses
Primary key: `response_id`.
Foreign keys:
- `run_id` → `runs(run_id)`
- `variant_id` → `query_variants(variant_id)`

Stores:
- provider + model identifiers
- request params JSON
- status (`ok | blocked | error | cached`)
- response text
- raw JSON payload (contains `prompt_hash`)
- latency and timestamp

### 7.4 Table: detections
Primary key: `detection_id`.
Foreign key: `response_id` → `llm_responses(response_id)`.

Stores:
- per-brand binary mention
- matched snippet
- optional rank position

## 8) UI behavior

### 8.1 Provider enablement
- Provider options displayed are only those whose client `is_configured()` returns true.

### 8.2 History tab
- Lists recent runs (up to 50) and allows selection to view raw responses and detections.

### 8.3 Response inspection
- For a selected response, UI displays:
  - provider, model, status
  - seed query and variant text
  - response text
  - stored raw JSON payload

## 9) Error handling and partial failures

- Redirect resolution failures do not stop the run; errors are recorded in redirect chain.
- Provider call failures return `status = error`, store `error_message`, and still insert a response row.
- Detection is still executed on `None` response text (yields `mentioned_binary = 0` for all brands).

## 10) Known limitations (by design)

- Detection is substring-based on the registrable domain; it will miss brand mentions without domains.
- Rank extraction only works for simple one-item-per-line lists that match the regex.
- Cache lookup uses a string `LIKE` match on `response_raw_json` to find `prompt_hash`.
- Query generation does not currently use LLM rewrite variants even though the architecture names “rewrite” as a potential method.

## 11) Extension points (future work)

If extending beyond the prototype, the lowest-risk upgrades are:
- Add LLM rewrite variants (store `variant_method = rewrite`, persist rewrite prompt and model used).
- Improve domain detection to handle URLs and bare domains (and set `mention_type` accordingly).
- Improve rank extraction using Markdown parsing, JSON tool outputs, or structured prompting.
- Replace cache `LIKE` query with a dedicated `prompt_hash` column (indexed).
