# Deployment Guide — Mini AEO Analytics (Prototype)

You asked "can you deploy it for me?" — I can’t directly deploy into a cloud account from this VS Code environment because it requires your hosting choice and your credentials. What I *can* do is give you copy/paste steps for a one-click deployment platform, and also provide container deployment instructions.

This repo is a Streamlit app. The entrypoint is:
- `app/streamlit_app.py`

## Option A (Recommended): Streamlit Community Cloud

This is the quickest way to get a public URL.

### 1) Push the repo to GitHub
- Create a GitHub repo
- Push this workspace to it

### 2) Create the Streamlit app
- Go to https://share.streamlit.io (Streamlit Community Cloud)
- Click **New app**
- Select your GitHub repo + branch
- Set **Main file path** to:
  - `app/streamlit_app.py`

### 3) Add secrets (API keys)
In the Streamlit Cloud UI, set secrets to match `.streamlit/secrets.toml.example`:

- `GEMINI_API_KEY = "..."`
- `OPENAI_API_KEY = "..."`
- `ANTHROPIC_API_KEY = "..."`

Minimum to test end-to-end: **one** provider key (Gemini is the simplest).

### 4) Deploy
- Click **Deploy**
- Open the app URL

#### Notes
- SQLite file `data/aeo_runs.sqlite3` will live in the Streamlit Cloud container filesystem.
- On free/community hosts, filesystem persistence may be limited/ephemeral. Treat it as a prototype artifact store, not durable storage.

## Option B: Docker (deploy to any container host)

This option is good for Azure Container Apps, AWS ECS, Render, Fly.io, etc.

### 1) Build the image
From the repo root:

- `docker build -t mini-aeo .`

### 2) Run locally
Create a secrets file by copying the example:
- Copy `.streamlit/secrets.toml.example` → `.streamlit/secrets.toml`
- Fill at least one API key

Then run:
- `docker run --rm -p 8501:8501 mini-aeo`

Open:
- http://localhost:8501

### 3) Provide secrets in a container host
Because the code reads keys via `st.secrets`, you have two common choices:

1) **Mount a secrets file** into the container at `/app/.streamlit/secrets.toml`.
2) Use your platform’s secret manager to write a file at runtime.

(If you want env-var based secrets instead, we can update the provider clients to fall back to `os.environ`.)

### 4) Persistence
If you want the SQLite DB to persist across container restarts, mount a volume to `/app/data`.

## Troubleshooting

- If the provider list is empty: secrets aren’t configured correctly.
- If a provider returns errors: check the key, model availability, quotas, and network.
- If rank is always N/A: the answer didn’t contain a line-based list matching the regex in `aeo/detection.py`.
