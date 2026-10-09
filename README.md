# ATLAS-Σ

Live demo: https://atlas-ptbu.onrender.com

A small scheduling demo for personal weekly planning, one-class academic timetabling, and laboratory resources.
All three scenarios share a validated constraint model and a real OR-Tools CP-SAT solver.

## Run

Python 3.12:

```sh
python -m venv .venv
# Activate the virtual environment, then:
pip install -r backend/requirements-lock.txt
python run_demo.py
```

The verified frontend production build is included in `frontend/dist` and served by FastAPI.
For frontend development, run `pnpm install --frozen-lockfile` and `pnpm dev` in `frontend`.
After editing frontend code, run `pnpm build` and commit the updated build.

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

## Tests

`python -m pytest backend/tests -q`

See `THIRD_PARTY.md` for dependencies and upstream references. Credentials, local databases, private requirements documents, and runtime logs are excluded from this repository.
