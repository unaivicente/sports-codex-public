# Getting started

## Requirements

- Python 3.11 or later: the code imports `datetime.UTC`.
- Node.js and npm. Vite's installed package declares the supported Node engine
  range; Node 22.12+ is one supported line. Use a compatible Node release.
- Git and Make for the documented root workflow.
- `ffmpeg` and `ffprobe` only for real local frame extraction. Neither is needed
  for the mock UI, timestamp planning, or tests using a fake command runner.

The verification environment used Python 3.11.7, Node 23.6.1 and npm 11.13.0.
There is no GPU requirement for current mock and preparation workflows.

## Install

```sh
git clone https://github.com/unaivicente/sports-codex-public.git
cd sports-codex-public
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r apps/api/requirements.txt
npm --prefix apps/web ci
make setup
```

On Windows, activate the virtual environment using its Scripts activation
command and run the Python/npm commands directly if Make is unavailable.
Python modules are imported from the repository root; there is no installable
root Python package configuration. The frontend lockfile is committed.

## Start the review demo

Terminal 1, with the virtual environment active:

```sh
python -m apps.api.server --host 127.0.0.1 --port 8000
```

Terminal 2, from the repository root:

```sh
npm --prefix apps/web run dev -- --host 127.0.0.1
```

Open the URL printed by Vite, normally `http://127.0.0.1:5173`. Check the API:

```sh
curl http://127.0.0.1:8000/health
```

Expected response fields are `status: "ok"` and `contract_version: "0.1.0"`.
Stop each server with Ctrl+C. Follow the [user guide](USER_GUIDE.md) for a demo.

## Run the separate FastAPI shell

```sh
python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8001 --reload
```

Visit `http://127.0.0.1:8001/docs` for interactive OpenAPI documentation,
`/redoc` for ReDoc, or `/openapi.json` for the schema. Its health route is
`/api/v1/health`.

This server has versioned `/api/v1` routes and different response shapes from
the demo server. The React client calls `/health` and `/api/...` and cannot
switch to FastAPI merely by changing the base URL. Use the demo server for the
UI; use FastAPI for its documented shell endpoints and model discovery.

## Configuration

| Setting | Consumer | Behavior |
| --- | --- | --- |
| `VITE_API_BASE_URL` | Vite / `apps/web/src/api.ts` | Defaults to `http://127.0.0.1:8000`; trailing slash is removed |
| `--host`, `--port` | Demo API CLI | Defaults to `127.0.0.1`, `8000` |
| `DB_PATH` | Make database/training targets | Defaults to `data/dev.sqlite3` |
| Other Make path variables | Make training/evaluation targets | See [development](DEVELOPMENT.md) |
| `APP_ENV`, `DATA_DIR`, `MODEL_REGISTRY_DIR`, `ONTOLOGY_DIR` | Root `.env.example` | Planning examples; current Python modules do not read these variables |

For another demo API port, start it with `--port 8002` and run:

```sh
VITE_API_BASE_URL=http://127.0.0.1:8002 npm --prefix apps/web run dev
```

Vite also supports an ignored `apps/web/.env.local` containing
`VITE_API_BASE_URL=http://127.0.0.1:8002`. Restart Vite after changing it.
Copying the root `.env.example` to `.env` does not configure Python paths or
automatically provide Vite configuration. Never commit local environment files.

## Verify and prepare data

```sh
make check
npm --prefix apps/web run build
make db-dev
make fine-tuning-prepare
make adapter-train
```

These data commands prepare independent SQLite/JSON fixtures. UI submissions
do not populate that database. See [storage](STORAGE.md).

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `python` missing or wrong version | Activate the virtual environment; verify `python --version` is 3.11+ |
| `No module named apps` / `packages` | Change to the repository root before running `python -m ...` |
| FastAPI import failure | Install `apps/api/requirements.txt` into the interpreter used by the command |
| Frontend shows backend unavailable | Run `apps.api.server`, check `/health`, and check `VITE_API_BASE_URL` |
| `/api/v1` works but UI fails | The UI requires the demo API's unversioned paths and payloads |
| Vite rejects Node version | Check the installed Vite package engine range and use a compatible runtime |
| Port already in use | Select a free API port and set the frontend base URL; use Vite's printed URL |
| FFmpeg executable not found | Install FFmpeg or pass `ffmpeg_path` / `ffprobe_path` to the ingestion function |
| `no such table: corrections` | Migrate or seed the selected database before training preparation |
| Training manifest has no examples | Inspect `skipped` reasons and correction validity/trust fields |
| Evaluation exits with status 1 | Inspect `promotion_decision`; a blocked promotion is an expected outcome |
