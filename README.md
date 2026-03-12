# Mini AEO Analytics Platform (Prototype)

A Streamlit prototype that measures how often a target brand appears in AI-generated answers vs competitors.

## What it does
- Accepts a target domain or landing page URL, competitor domains/URLs (comma-separated), and seed queries.
- Generates 5–10 query variations per seed.
- Sends queries to one or more LLMs (Gemini / GPT / Claude) depending on which API keys are present in Streamlit secrets.
- Stores raw responses and metadata in SQLite for reproducibility.
- Detects domain mentions and computes AEO metrics (Share of Voice, average rank when list-like, visibility by provider).
- Exports a Markdown report + CSVs with excerpts and links to raw response records.

## Setup
1. Create a Python venv.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Configure keys via Streamlit secrets:
   - Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`
   - Fill `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` as needed
4. Run:
   - `streamlit run app/streamlit_app.py`

## Deployment
See `DEPLOYMENT.md` for Streamlit Community Cloud and Docker instructions.

## Provider enablement
- Providers are selectable only if the corresponding secret exists.
- Keys are never stored in SQLite and are never logged.

## Notes
- This is a prototype; reproducibility is achieved by persisting raw outputs per run, not by assuming deterministic LLM behavior.
- Secrets are never written to SQLite.
