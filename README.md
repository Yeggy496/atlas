# ATLAS-Σ

Website: https://atlas-ptbu.onrender.com

A small scheduling application for personal weekly planning, one-class academic timetabling,
laboratory resources, meeting rooms, and production jobs.
All five scenarios share a validated constraint model and a real OR-Tools CP-SAT solver.

Current update: [v0.1.6 product interface notes](docs/RELEASE_0.1.6.md).
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
Start: `ATLAS_SOLVE_SECONDS=30 ATLAS_SOLVER_WORKERS=1 ATLAS_DIAGNOSIS_SECONDS=2 uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT`
Health check: `/api/health`.

## Features and boundaries

- Real calendars, resource allocation, weighted objectives, conflict diagnosis with verified repair candidates, and rescheduling.
- CSV/XLSX activity imports using the downloadable templates; maximum 2 MB and 100 rows.
- Constraints require validation and explicit user review before solving.
- Default `LLM_PROVIDER=demo` is a limited offline rule parser, clearly identified in the UI.
- OpenAI and DeepSeek provider implementations accept server-only environment variables; real API calls require configuration and verification.
- Time resolution is 30 minutes. This demo targets small inputs, not a whole school.
- No accounts or per-user history isolation. Public visitors share demo history; avoid sensitive personal inputs.
- Free hosting can sleep when idle. SQLite history on ephemeral storage may be lost after restarts or deployments.
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

`backend/tests/test_llm_live.py` performs a real end-to-end provider call. It is skipped unless
`ATLAS_LLM_LIVE_TEST=1` and a key are set, so the offline suite and CI stay green without credentials.

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

*Measured 2026-10 on this project:* the official `https://api.deepseek.com` endpoint with
`DEEPSEEK_MODEL=deepseek-chat` parses every bundled sample well inside a demo budget
(lab 5.2 s, life 13.0 s; `POST /api/constraints/parse` returned 200 in 5.0 s).
A BUPT campus gateway (`deepseek-v4-flash`) answered short requests in 2-9 s, but timed out after
180-300 s when it had to emit a whole modified problem, so prefer the official endpoint, or another
fast OpenAI-compatible model, when enabling the real provider on the hosted demo.

## Tests

`python -m pytest backend/tests -q`

See `THIRD_PARTY.md` for dependencies and upstream references. Credentials, local databases, private requirements documents, and runtime logs are excluded from this repository.
