# API reference

There are two API implementations. The React client uses the unversioned demo
server. FastAPI is a separate shell with `/api/v1` routes. Both are local
interfaces with mock predictions and non-persistent correction acknowledgements.

## Demo API

Source: [`apps/api/server.py`](../apps/api/server.py) and
[`mock_payloads.py`](../apps/api/mock_payloads.py).

```sh
python -m apps.api.server --host 127.0.0.1 --port 8000
```

| Method | Path | Input | Result |
| --- | --- | --- | --- |
| GET | `/health` | None | `status`, `contract_version` |
| GET | `/api/ontologies` | None | `data.ontologies` with labels, `default_ontology_id` |
| GET | `/api/sports` | None | `data.sports` with nested ontologies, defaults |
| GET | `/api/predictions/mock` | Optional query `ontology_id` | `data.predictions`, generated fixture video ID |
| POST | `/api/predictions/mock` | JSON with optional `ontology_id`, `video_id` | Mock list and model/ontology provenance |
| GET | `/api/feedback/quality` | Optional query `ontology_id` | `data.dashboard` fixture analytics |
| GET | `/api/active-learning/queue` | Optional query `ontology_id` | `data.active_learning` demo queue |
| POST | `/api/videos` | Request bytes; optional filename/content-type headers | HTTP 201, `data.video`, bytes discarded |
| POST | `/api/corrections` | Full human-correction contract | HTTP 201, validated echo and provenance |
| OPTIONS | Any path | CORS preflight | HTTP 204 |

Except for health and errors, responses use this envelope:

```json
{
  "contract_version": "0.1.0",
  "data": {}
}
```

### Discover ontologies and request predictions

```sh
curl http://127.0.0.1:8000/api/ontologies
curl -X POST http://127.0.0.1:8000/api/predictions/mock \
  -H 'Content-Type: application/json' \
  -d '{"ontology_id":"football-local-mvp","video_id":"demo-video"}'
```

The response's `data` contains `video_id`, `ontology_id`, `ontology_version`,
`model_version`, and `predictions`. Each prediction is a one-second interval.
At most three are generated, at timestamps 0, 8 and 16. Labels come from active
ontology labels, not video analysis. The fixture timestamp `created_at` is the
request time, so entire response bytes are not deterministic across requests.

### Upload acknowledgement

```sh
curl -X POST http://127.0.0.1:8000/api/videos \
  -H 'X-Local-Filename: sample.mp4' \
  -H 'X-Local-Content-Type: video/mp4' \
  -H 'Content-Type: video/mp4' \
  --data-binary @sample.mp4
```

The browser sends multipart form data with the same two local headers. The
server does not parse multipart data: it counts and discards the request body.
`byte_count` therefore includes multipart overhead for browser uploads.
`data.video` includes `video_id`, `filename`, `content_type`, `byte_count`,
`status: "accepted_stub"`, `storage: "not_persisted"`, and
`processing: "not_started"`. No file-format validation or ingestion occurs.

### Submit a correction

Save a complete correction as described in [data contracts](DATA_CONTRACTS.md),
then submit it:

```sh
curl -X POST http://127.0.0.1:8000/api/corrections \
  -H 'Content-Type: application/json' \
  --data-binary @correction.json
```

`data` contains `accepted: true`, the echoed `correction`,
`preserved_source_prediction_ids`, `source_model_versions`, and
`source_ontology_versions`. Acceptance means structural/semantic validation,
not reviewer approval or database persistence.

### Errors and CORS

| Status | Meaning / response |
| --- | --- |
| 400 | Malformed JSON, non-object JSON, invalid request value; `{"error":"..."}` |
| 404 | Unknown route or ontology; `{"error":"..."}` |
| 422 | Contract rejection; `{"error":"contract validation failed","errors":["..."]}` |

The server sets `Access-Control-Allow-Origin: *`, allows `GET, POST, OPTIONS`,
and allows `Content-Type`, `X-Local-Filename`, `X-Local-Content-Type`. It has no
authentication, rate limits, persistence or public-service hardening.

## FastAPI shell

Source: [`apps/api/main.py`](../apps/api/main.py).

```sh
python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8001 --reload
```

Root `/` reports API metadata. `/docs`, `/redoc`, and `/openapi.json` expose
interactive and machine-readable documentation. Every route below is prefixed
with `/api/v1`.

| Method | Relative path | Input / behavior |
| --- | --- | --- |
| GET | `/health` | Health with contract and API versions |
| POST | `/videos` | Multipart `file`; returns stub metadata without storage |
| POST | `/predictions` | Required `video_id`; optional integer `timestamp >= 0`, `sport_id`, `ontology_version` |
| POST | `/predictions/mock` | Alias of `/predictions`; returns a single `data.prediction` |
| POST | `/corrections` | Full correction payload; validates and echoes without persistence |
| GET | `/exports` | Lists `predictions_json`, `corrections_json`, `training_dataset` stubs |
| POST | `/exports/{export_type}` | Optional `video_id`, `ontology_version`; returns `file_written: false` |
| GET | `/active-learning/queue` | Optional `sport_id`, `ontology_version`; demo inputs |
| POST | `/active-learning/queue` | Optional selectors, `predictions`, `corrections`; scores supplied inputs |
| POST | `/admin/model-discovery/refresh` | Explicit metadata discovery and local registry write |
| GET | `/sports` | Sport catalog with compact ontology entries |
| GET | `/ontologies` | Optional `include_labels=true`; ontology summaries |
| GET | `/ontologies/{ontology_version}` | Full ontology definition |

Successful data envelopes additionally contain `api_version: "v1"`. FastAPI
uses HTTP 200 for the shell POST routes; validation errors use 422 and missing
resources use 404. Errors use FastAPI's `detail` field, unlike the demo API.
Unsupported export types use 404; unsupported discovery source/trigger uses 400.

```sh
curl http://127.0.0.1:8001/api/v1/health
curl -X POST http://127.0.0.1:8001/api/v1/predictions \
  -H 'Content-Type: application/json' \
  -d '{"video_id":"demo-video","sport_id":"football","timestamp":0}'
curl -X POST http://127.0.0.1:8001/api/v1/active-learning/queue \
  -H 'Content-Type: application/json' \
  -d '{"sport_id":"football"}'
```

### Model discovery request

```sh
curl -X POST http://127.0.0.1:8001/api/v1/admin/model-discovery/refresh \
  -H 'Content-Type: application/json' \
  -d '{"trigger":"admin_refresh","source_mode":"static","sport_id":"football"}'
```

| Field | Default / meaning |
| --- | --- |
| `trigger` | `admin_refresh`; also accepts `setup` |
| `source_mode` | `static`; `huggingface` explicitly enables public model metadata requests |
| `sport_id`, `ontology_version` | Optional ontology selection |
| `tasks_by_modality` | Optional mapping of modality to task names |
| `sample_clips` | Default local descriptor; each has ID, duration, timestamps and modalities |
| `limit_per_task` | 5, constrained to 1–25 |
| `registry_path` | Optional local output path; default `data/model_registry/model_discovery_registry.json` |

Discovery scores metadata and emits synthetic ontology-backed smoke-test
evidence. It does not load or benchmark model weights. A clip's `local_path` is
a descriptor rather than an instruction to execute inference on that file.
The route name does not enforce administrator authentication. Keep this API
bound to loopback; it accepts a registry path and can write local files.
