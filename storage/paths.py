from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def data_dir() -> Path:
    path = project_root() / "data"
    path.mkdir(exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "aeo_runs.sqlite3"


def schema_path() -> Path:
    return project_root() / "storage" / "schema.sql"


def reports_out_dir() -> Path:
    path = project_root() / "reports" / "out"
    path.mkdir(parents=True, exist_ok=True)
    return path
