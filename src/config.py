"""Shared paths and env for the docs pipeline.

Project layout:
  <repo>/
    .env
    apidog_modules.json
    prompts/
    data/                   # pulled source (SOURCE_REPO_DIR)
    data/*.openapi.json     # generated specs / markdown
    src/*.py                # scripts (this package)
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# src/ → project root
SRC_DIR = Path(__file__).resolve().parent
ROOT = SRC_DIR.parent

# Always load repo-root .env regardless of cwd
load_dotenv(ROOT / ".env")
load_dotenv()  # allow cwd overrides


def _path_from_env(name: str, default: str | Path) -> Path:
    raw = os.environ.get(name)
    path = Path(raw) if raw else Path(default)
    return path if path.is_absolute() else (ROOT / path)


SOURCE_REPO_URL = os.environ.get("SOURCE_REPO_URL", "")
SOURCE_DIR = _path_from_env("SOURCE_REPO_DIR", "")
# Optional branch override; empty → origin/HEAD, then main/master
SOURCE_BRANCH = os.environ.get("SOURCE_BRANCH", "").strip()
# Private HTTPS clones (GHA secret). Falls back to GITHUB_TOKEN when set.
SOURCE_REPO_TOKEN = (
    os.environ.get("SOURCE_REPO_TOKEN", "").strip()
    or os.environ.get("GITHUB_TOKEN", "").strip()
)

# OpenAPI specs / markdown for auto_upload: data/<ModuleName>.*
DATA_DIR = _path_from_env("DATA_DIR", "data")
PROMPTS_DIR = _path_from_env("PROMPTS_DIR", "prompts")
MODULE_MAP_PATH = _path_from_env("APIDOG_MODULE_MAP", "apidog_modules.json")

# generate_openapi.py — export from pulled .NET API
OPENAPI_PROJECT = os.environ.get("OPENAPI_PROJECT", "")
OPENAPI_MODULE_NAME = os.environ.get("OPENAPI_MODULE_NAME", "")
OPENAPI_DOCUMENT_PATH = os.environ.get("OPENAPI_DOCUMENT_PATH", "")
# Discover and export every OpenAPI-capable API project under SOURCE_REPO_DIR
OPENAPI_ALL = os.environ.get("OPENAPI_ALL", "").strip().lower() in {"1", "true", "yes", "on"}
# Optional comma-separated filter of project stems or paths (e.g. Catalog.API,Ordering.API)
OPENAPI_PROJECTS = os.environ.get("OPENAPI_PROJECTS", "").strip()
CURSOR_MODEL = os.environ.get("CURSOR_MODEL", "")
