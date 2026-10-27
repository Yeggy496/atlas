# OptiDay

Website: https://atlas-ptbu.onrender.com

A small scheduling application for personal weekly planning, one-class academic timetabling,
laboratory resources, meeting rooms, and production jobs.
All five scenarios share a validated constraint model and a real OR-Tools CP-SAT solver.

Current version: **v0.2.3 — OptiDay**. Long structured-output budgets, one bounded validation repair,
and a reversible scene suggestion for personal plans entered in a different workspace.
[Current fix and verification scope](docs/RELEASE_0.2.3.md).
The v0.2.2 identity, palette and compatible browser-data upgrades are retained. [Interface release](docs/RELEASE_0.2.2.md).
Product workflow notes: [v0.1.9](docs/RELEASE_0.1.9.md).
Local workspace notes: [v0.1.7](docs/RELEASE_0.1.7.md).
Product interface notes: [v0.1.6](docs/RELEASE_0.1.6.md).
DeepSeek setup and connection verification: [v0.1.5 notes](docs/RELEASE_0.1.5.md).
Verified capability report before this update: [2026-10-12 review](docs/REVIEW_2026-10-12.md).
The default provider remains `demo`; real model calls require server-side configuration.
The existing Render website was configured with the official DeepSeek provider and verified on
2026-10-12; local clones still need their own server-side key and settings.
The report distinguishes working website features from backend-only capabilities and remaining limitations.

## Run

Python 3.12:

```sh
python -m venv .venv
# Activate the virtual environment, then:
pip install -r backend/requirements-lock.txt
python run_demo.py
```

The verified frontend production build is included in `frontend/dist` and served by FastAPI, so the
committed bundle is what the live demo ships.
For frontend development, run `pnpm install --frozen-lockfile` and `pnpm dev` in `frontend`.
After editing frontend code, rebuild and commit the bundle in one step:

```sh
scripts/build_frontend.ps1   # pnpm install --frozen-lockfile && pnpm build, then git add frontend/dist
```

Enable the tracked guard once per clone so a frontend change cannot be committed without the rebuilt bundle:

```sh
git config core.hooksPath .githooks
```

## Deploy

`render.yaml` defines one free native Python web service. The service uses the platform-provided HTTPS domain.
Build: `pip install -r backend/requirements-lock.txt && python run_demo.py --check`
Start: `OPTIDAY_SOLVE_SECONDS=30 OPTIDAY_SOLVER_WORKERS=1 OPTIDAY_DIAGNOSIS_SECONDS=2 uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT`
Health check: `/api/health`.

## Features and boundaries

- Real calendars, resource allocation, weighted objectives, conflict diagnosis with verified repair candidates, and rescheduling.
- CSV/XLSX activity imports using the downloadable templates; maximum 2 MB and 100 rows.
- Constraints require validation and explicit user review before solving.
- Workspaces auto-save in the current browser, separately for each scenario. Reloads and reopening restore inputs, drafts, settings, and the last result without loading or solving the preset again. Different browser profiles/devices do not sync; clearing site data removes the local copy.
- New visitors start with an empty plan; a complete example is an explicit choice. Cached workspaces are preserved. New plans and examples use the browser's current week.
- Same-scenario tab conflicts block stale saves and offer opening the latest copy, keeping the current edit, or backing it up. Input that has not been recognized blocks solving until the user parses it or explicitly chooses only the existing model.
- Start a personal blank plan, choose its week, manage resources, undo edits, and download/restore workspace backups on another computer. Imported backups require review and a new solve.
- Edit names, search/filter tasks, repeat activities on selected days, and edit/fix/unlock events from the calendar. Up to ten content edits can be undone during the current session; reloading or changing scenarios resets undo records.
- View a week, one day, or an agenda. Mobile defaults to the agenda, offers history navigation, and scrolls to the generated plan. Early/late activities cannot be silently hidden.
- CSV/XLSX accepts Chinese headers, current resource IDs or unambiguous names, and native spreadsheet time cells. Imports append activities and disclose potential duplicates. TXT/PDF preserves the extracted text up to 200,000 characters; the user parses it in chunks of up to 4,000 characters without losing the remaining text.
- Event details retrieve deterministic solver facts first. AI narration is requested explicitly and cached in the current session; opening an event does not automatically incur a model call.
- The last 12 solve runs stay in the current browser. Public deployments neither expose nor persist shared visitor histories by default; `/api/history` returns an empty list. `OPTIDAY_SERVER_HISTORY=true` is only for a trusted single-user local service.
- Chinese PDF and Excel exports use the real on-screen assignments; rescheduling displays changes from the previous plan.
- Default `LLM_PROVIDER=demo` is a limited offline rule parser, clearly identified in the UI.
- OpenAI and DeepSeek provider implementations accept server-only environment variables; real API calls require configuration and verification.
- Time resolution is 30 minutes. Individual activities stay within one calendar day; split an overnight activity into two parts. The application targets small inputs, not a whole school.
- No accounts or cross-device synchronization. Solver inputs reach the server; AI parsing and narration send relevant data to the configured model provider.
- Free hosting can sleep when idle. Local browser workspaces and histories survive server redeploys; clearing browser storage removes them, so download backups before moving devices.
- Repairs relax individual constraints and verify feasibility; they do not prove a globally minimal conflict core.

## LLM provider

`LLM_PROVIDER` selects the constraint parser: `demo` (offline rule parser, no key), `openai`, or `deepseek`.
The real providers call an OpenAI-compatible `/chat/completions` endpoint and require server-side env vars:

| Variable | Purpose |
| --- | --- |
| `LLM_PROVIDER` | `demo` (default), `openai`, or `deepseek` |
| `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` | provider credential (never commit) |
| `OPENAI_MODEL` / `DEEPSEEK_MODEL` | model name (defaults `gpt-4.1-mini` / `deepseek-flash`) |
| `OPENAI_BASE_URL` / `DEEPSEEK_BASE_URL` | optional OpenAI-compatible gateway override (blank = official endpoint) |
| `OPENAI_TIMEOUT` / `DEEPSEEK_TIMEOUT` | per-request seconds (defaults `35` / `90`) |
| `OPENAI_MAX_TOKENS` / `DEEPSEEK_MAX_TOKENS` | structured task output budgets (defaults `16384` / `24576`; supported range `1024–32768`) |

`backend/tests/test_llm_live.py` performs a real end-to-end provider call. It is skipped unless
`OPTIDAY_LLM_LIVE_TEST=1` and a key are set, so the offline suite and CI stay green without credentials.

### Turning on a real provider on Render

The deployment template defaults to `LLM_PROVIDER=demo` so a new deployment works without secrets.
The existing hosted website now uses the official DeepSeek endpoint. To enable a real model on another deployment:

1. Set `LLM_PROVIDER` to `openai` or `deepseek` in the Render dashboard (or `render.yaml`).
2. Add the matching `*_API_KEY` as a secret environment variable. Never commit it.
3. Optionally point `*_BASE_URL` at an OpenAI-compatible gateway and raise `*_TIMEOUT`.
   For the current official DeepSeek endpoint use `LLM_PROVIDER=deepseek`,
   `DEEPSEEK_MODEL=deepseek-flash`, and `DEEPSEEK_TIMEOUT=90`.
   The backend disables thinking for these JSON extraction calls.
4. Prove the server can reach the model before showing the demo:

   `python scripts/check_llm.py --scenario academic`

The check prints the provider, model, base URL, and whether the key is present (never the key itself), and exits non-zero on failure.

*Measured 2026-10-12 on the deployed project:* the official endpoint with
`DEEPSEEK_MODEL=deepseek-flash` parsed a full personal plan with a new fixed meeting
in 17.41 seconds. This is one recorded call, not a latency guarantee or an accuracy benchmark.
Model gateways must be reachable from the hosting server; test them before use.

## Tests

`python -m pytest backend/tests -q`

Start the application, then run `python scripts/check_gray_workflows.py --url http://127.0.0.1:8000` for focused real-browser checks. The other `scripts/check_*workflows.py` checks cover complete resource, backup, repair, and persistence journeys. These tests use isolated browser data. Network and quota failures are simulated deliberately; valid schedules are produced by CP-SAT.

The single-process server bounds concurrent solves/diagnosis to 2 and model requests to 2 by default (`OPTIDAY_CONCURRENT_SOLVES` / `OPTIDAY_CONCURRENT_MODEL_CALLS`, supported range 1–8). Requests above capacity receive HTTP 429 with `Retry-After: 3`; the UI preserves current content and offers retry. This protects a small instance; it is not a throughput benchmark or a distributed queue.

## Upgrading an existing installation

Existing browser plans, solve history and downloaded backups are accepted by OptiDay. Validated plans are copied
to the new browser storage key; the original copy is kept for recovery. A newly created OptiDay backup uses
the new product name. Public server history remains disabled by default.

Use `OPTIDAY_*` for new server settings. Existing settings with the previous product prefix remain supported by
`backend/app/config.py`; an explicit new value wins. Provider keys such as `DEEPSEEK_API_KEY` do not change.
The repository and hosted service retain their existing addresses so shared links continue working.

`pnpm build` now updates both `frontend/dist` and `backend/app/webapp`. Commit both generated folders with
frontend changes. `python scripts/check_brand_upgrade.py --url http://127.0.0.1:8000` verifies old-data recovery,
the new identity, and export metadata. Fresh three-scenario benchmark results are in `docs/evidence-20261027/`;
they compare simple baselines and CP-SAT on preset data, not model accuracy or real user outcomes.

See `THIRD_PARTY.md` for dependencies and upstream references. Credentials, local databases, private requirements documents, and runtime logs are excluded from this repository.
