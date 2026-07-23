# Pipeline + sample API (test harness)

This repo is [FabianGosebrink/ASPNETCore-WebAPI-Sample](https://github.com/FabianGosebrink/ASPNETCore-WebAPI-Sample) plus the Apidog docs pipeline (`src/`, `prompts/`, `.github/workflows/apidog-docs-pipeline.yml`).

## One-time setup

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Fill `.env` with your Apidog values. Ensure `apidog_modules.json` has module `SampleWebApiAspNetCore` with a real Apidog `moduleId`.

## Local manual test (recommended first)

```bash
# OpenAPI export + Apidog upload only (no Cursor, no email, no git pull)
python src/orchestrator.py --skip-pull --skip-docs --skip-email --module SampleWebApiAspNetCore
```

Expect `data/SampleWebApiAspNetCore.openapi.json` and a successful Apidog import.

## GitHub Actions

1. Push this repo to GitHub.
2. Add secrets: `APIDOG_BASE_URL`, `APIDOG_PROJECT_ID`, `APIDOG_ACCESS_TOKEN`.
3. Actions → **Apidog docs pipeline** → **Run workflow** (leave `run_docs` / `run_email` false for the first run).

## Sample API

- Solution: `SampleWebApiAspNetCore.sln`
- Project: `SampleWebApiAspNetCore/SampleWebApiAspNetCore.csproj`
