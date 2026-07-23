# Apidog documentation pipeline — tasks & architecture

## Context

The global goal is a **monthly automated pipeline** that:

1. Pulls a source microservice repository
2. Enriches documentation with Cursor (narrative markdown + endpoint XML comments)
3. Exports **OpenAPI** from the .NET API
4. Uploads endpoints, schemas, and docs into **Apidog** (self-hosted)
5. (Later) emails the generated README; optional DB topology

**Why:** Keep Apidog in sync with code without hand-maintaining Swagger/docs every release. Cursor covers human-readable docs; OpenAPI covers machine-importable API surface.

**Current pilot targets (generalization):** small public C# Web APIs under `data/` —

- [kathleenwest/ContosoPizzaWebApiDemo](https://github.com/kathleenwest/ContosoPizzaWebApiDemo) → `data/contosopizza/`
- [FabianGosebrink/ASPNETCore-WebAPI-Sample](https://github.com/FabianGosebrink/ASPNETCore-WebAPI-Sample) → `data/sample-webapi/`

(Former TodoApi pilot removed; re-add via `pull_source.py` if needed.)

**Apidog host:** configured via `APIDOG_BASE_URL` / `APIDOG_PROJECT_ID` / `APIDOG_ACCESS_TOKEN` in `.env`. Known API limits are documented in [`limits.md`](limits.md).

---

## Architecture

### Repo layout

```text
test_automation/
├── .env                          # secrets (gitignored)
├── apidog_modules.json           # module name → Apidog moduleId
├── prompts/                      # Cursor prompt sources (steps 2–4)
├── data/
│   ├── <source-clone>/           # pulled source clone (gitignored)
│   ├── <Module>.readme.md        # step 2 output
│   ├── <Module>.intro.md         # step 3 output
│   └── <Module>.openapi.json     # step 5 output
├── info/
│   ├── tasks.md                  # this file
│   └── limits.md                 # Apidog capability matrix
└── src/
    ├── config.py                 # paths + env
    ├── pull_source.py            # step 1
    ├── cursor_cli.py             # shared Cursor CLI runner
    ├── run_cursor_prompt.py      # one prompt, reusable
    ├── run_cursor_docs.py        # orchestrate steps 2–4
    ├── generate_openapi.py       # step 5
    ├── auto_upload.py            # step 6
    ├── send_email.py             # step 7
    └── orchestrator.py           # steps 1–7
```

### Pipeline flow

```text
┌─────────────┐    ┌──────────────────┐    ┌───────────────────┐
│ 1 pull_source│───▶│ 2–4 Cursor docs  │───▶│ 5 generate_openapi│
│  → data/<…>  │    │  readme/intro/xml│    │  → .openapi.json  │
└─────────────┘    └──────────────────┘    └─────────┬─────────┘
                                                     │
                                                     ▼
                                           ┌─────────────────┐
                                           │ 6 auto_upload   │───▶ Apidog module
                                           │  (+ readme/intro)│
                                           └─────────────────┘
```

| Step | Script | Inputs | Outputs |
|------|--------|--------|---------|
| 1 | `pull_source.py` | `--repo` / `SOURCE_REPO_URL`, git | `data/<clone>/` on main/master |
| 2 | `run_cursor_docs.py` (or `run_cursor_prompt.py`) | `prompts/readme-generation-prompt.md` | `data/<Module>.readme.md` |
| 3 | same | `prompts/service-introduction-page.md` | `data/<Module>.intro.md` |
| 4 | same | `Prompts/prompt-cursor-xml-comments 2.md` | In-place `.cs` edits under clone |
| 5 | `generate_openapi.py` | Build-time OpenAPI only (`--project` / `--all`; no live app) | `data/<Module>.openapi.json` (+ `x-apidog-folder`) |
| 6 | `auto_upload.py` | OpenAPI + module map | Apidog REST `import-openapi` (endpoints/schemas only) |
| 7 | `send_email.py` | `data/<Module>.readme.md` (+ `.intro.md`) | Email via SMTP (`REPORT_EMAIL_TO`) |

**Cursor reuse:** `run_cursor_prompt.py` runs any single prompt (`--out` or `--inplace`). `run_cursor_docs.py` chains steps 2–4 with the prompts listed in the plan below.

### Design choices (for future prompts / agents)

- **Apidog modules** cannot be created via APS token (403) — create once in UI, map IDs in `apidog_modules.json`.
- **Markdown pages** have no REST API — do **not** invent fake `/_docs` endpoints. README/intro are emailed by step 7 (`send_email.py`).
- **Cursor** uses the **CLI** (`agent`), not Python `cursor-sdk` (Windows bridge issues). Auth: `agent login` or `CURSOR_API_KEY`.
- **OpenAPI** is generated at **build time** (`Microsoft.Extensions.ApiDescription.Server` / `OpenApiGenerateDocuments`) — the script does not start the API. Tags are copied to `x-apidog-folder` for Apidog folders. Export may add the ApiDescription.Server package to the local clone when missing.
- **Step 4** mutates the local clone only; CI should use clean pull. Re-run step 5 after step 4 so descriptions reach Apidog.
- **Secrets** live in `.env` only — never in prompts or committed examples.
- **Per-repo knobs** (until a multi-repo runner exists): `--source-dir`, `--project`, `--module`.
- **Module naming:** `OPENAPI_MODULE_NAME` = `apidog_modules.json` key = `data/<Name>.openapi.json` stem.
- **Email** uses SMTP (`SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `REPORT_EMAIL_TO`).

### Commands (quick reference)

Configure the active target in `.env`, then:

```bash
python src/pull_source.py
python src/run_cursor_docs.py
python src/generate_openapi.py
python src/auto_upload.py
python src/send_email.py
# or: python src/orchestrator.py
```

---

## Plan

0) manually create project, empty modules on apidog
0.1) enter modules and their IDs inside apidog_modules.json
1) script pulls the repo to a folder. switches to main or master branch
2) cursor CLI   runs readme-generation-prompt.md
3) cursor CLI   runs service-introduction-page.md
4) cursor CLI   runs prompt-cursor-xml-comments 2.md
5) generates OpenAPI at build time (data/<Module>.openapi.json)
6) OpenAPI uploads automatically to Apidog (no markdown endpoints)
7) README (+ intro) emailed via SMTP (`REPORT_EMAIL_TO`)

Extra) Create a topology of the database

### Generalization checklist (in progress)

- [x] Remove TodoApi clone + generated `Todo.*` artifacts from `data/`
- [x] Pull 2 small public C# Web API samples for smoke tests
- [x] Drop Todo-hardcoded defaults (`SOURCE_REPO_DIR`, `OPENAPI_PROJECT`, `--todo-app-dir` → `--source-dir`)
- [x] Confirm OpenAPI export works on Swashbuckle samples (build-time via ApiDescription.Server)
      - ContosoPizza → `data/ContosoPizza.openapi.json`
      - SampleWebApi → `data/SampleWebApi.openapi.json`
- [ ] Run Cursor docs steps against one sample
- [ ] Map sample modules in Apidog + upload
- [ ] Later: repeatable multi-repo script / config list
