# API applications

Two local APIs are implemented here. The React client uses the first one.

| Entry point | Launch from repository root | Routes |
| --- | --- | --- |
| Standard-library demo | `python -m apps.api.server --host 127.0.0.1 --port 8000` | `/health`, `/api/...` |
| FastAPI shell | `python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8001 --reload` | `/api/v1/...`, `/docs`, `/openapi.json` |

Install `requirements.txt` for FastAPI and its tests. The demo server uses only
Python's standard library. It provides embedded football/basketball ontologies,
mock predictions, feedback dashboard fixtures and an active-learning demo queue.
FastAPI reads the JSON ontology registry, also scores supplied review inputs,
and exposes explicit model metadata discovery with local registry persistence.

Uploads and corrections are acknowledged without being saved by either API.
FastAPI export routes are stubs. There is no real model inference or production
authentication. The route shapes and response structures differ; changing the
frontend's base URL alone does not make it compatible with FastAPI.

See [API reference](../../docs/API_REFERENCE.md),
[setup](../../docs/GETTING_STARTED.md) and
[data contracts](../../docs/DATA_CONTRACTS.md).
