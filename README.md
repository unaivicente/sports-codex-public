# Sports Metadata Labeller

A local-first workbench for reviewing ontology-driven sports video metadata.
The project combines a React review interface, Python mock prediction APIs,
versioned data contracts, SQLite development storage, and local tools for
preparing correction datasets and evaluating candidate models.

**Status: development prototype.** Predictions are deterministic mocks. Video
uploads and correction submissions in the UI are acknowledged without being
saved. The media, database, and model lifecycle utilities work independently;
they are not yet connected into an end-to-end processing service.

Public repository: [unaivicente/sports-codex-public](https://github.com/unaivicente/sports-codex-public).
Start with the [documentation index](docs/README.md).

## Run the review demo

Use Python 3.11+ and a Node.js version supported by the checked-in Vite package
(its engine range includes Node 22.12+). Run commands from the repository root.

```sh
git clone https://github.com/unaivicente/sports-codex-public.git
cd sports-codex-public
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r apps/api/requirements.txt
npm --prefix apps/web ci
python -m apps.api.server --host 127.0.0.1 --port 8000
```

In a second terminal, from the repository root:

```sh
npm --prefix apps/web run dev -- --host 127.0.0.1
```

Open the URL printed by Vite, normally `http://127.0.0.1:5173`. Select a local
MP4, select a sport and ontology, request mock predictions, then review a label
and submit a correction. The feedback dashboard displays fixture data.

The demo API itself needs only the Python standard library. Installing the
requirements also enables the separate FastAPI shell and its tests. The frontend
currently expects the **unversioned demo API** above. See
[getting started](docs/GETTING_STARTED.md) for the FastAPI alternative and setup
details.

## What is implemented

| Area | Current behavior |
| --- | --- |
| Review UI | Local video preview, sport/ontology selection, mock timeline, confirm/relabel form, fixture feedback dashboard |
| APIs | Standard-library demo API and separate versioned FastAPI shell |
| Contracts | Five JSON Schemas, Python runtime validators, manually maintained TypeScript types |
| Ontology | Football/basketball demo fixtures; two football JSON definitions; validation and versioned evolution |
| Media | Exact rational frame timestamp planning and local MP4 frame extraction with FFmpeg |
| Extraction/fusion | Four deterministic modality mocks and one-second evidence grouping |
| Active learning | Ranked review queue with explainable flags and preserved provenance |
| Storage | SQLite migration, constraints, and deterministic development seed |
| Training preparation | Filtered correction manifests and versioned JSON adapter/label-head artifacts |
| Model lifecycle | Metadata discovery, local JSON registry, evaluation and promotion recommendations |

Real model inference, audio track extraction, probabilistic labelling, temporal
smoothing, persistent API workflows, and production authentication remain
unfinished. [Implementation status](docs/STATUS.md) records the boundaries.

## Develop and verify

```sh
make setup
make check
npm --prefix apps/web run build
make db-dev
make fine-tuning-prepare
make adapter-train
```

`make setup` creates directories; it does not install dependencies. `make dev`
prints launch commands; it does not start servers. `make check` checks the
repository structure and environment ignore rules, then runs backend and
frontend tests. Database and training commands write ignored files under `data/`.

See [contributing](CONTRIBUTING.md), the [command reference](docs/DEVELOPMENT.md),
and [storage guide](docs/STORAGE.md).

## Design principles

- Keep media and processing local. Optional Hugging Face discovery reads model
  metadata only when explicitly requested.
- Select labels from ontology definitions rather than embedding sport labels
  in inference code.
- Preserve evidence, model version, and ontology version on predictions.
- Preserve source prediction snapshots and reviewer provenance on corrections.
- Apply validity and trust policies before including feedback in training data.

## Public access and licensing

Code and documentation are published together in this repository; see
[public access](docs/PUBLIC_ACCESS.md). No project license file is currently
included. Public visibility does not specify a reuse license.
