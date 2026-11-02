# Contributing

Start with [getting started](docs/GETTING_STARTED.md) and the
[implementation status](docs/STATUS.md). The repository contains a working
prototype and independent local tools; some end-to-end workflows remain stubs.

## Local workflow

1. Sync with the repository's default branch and create a focused working branch.
2. Use Python 3.11+ in a virtual environment and install
   `apps/api/requirements.txt`; install frontend dependencies with
   `npm --prefix apps/web ci`.
3. Run `make check` and `npm --prefix apps/web run build`.
4. Run the two demo servers using the commands in the getting-started guide.
5. Update relevant guides and package READMEs when behavior changes.
6. Submit a pull request describing the change, how it was verified and any
   remaining limitations.

`make setup` creates directories. `make dev` prints startup commands. Neither
installs dependencies or starts an application. Root `.env.example` variables
are illustrative; see the guide for settings the code actually consumes.

## Project conventions

- Keep processing and media local; make any metadata-network integration explicit.
- Resolve labels from ontology data rather than hard-coding sports in inference logic.
- Preserve evidence, timestamps, model and ontology versions on predictions.
- Keep immutable source snapshots and reviewer/trust provenance on corrections.
- Update JSON Schema, Python validators and TypeScript mirrors together.
- Add numbered SQLite migrations instead of rewriting shared applied migrations.
- Keep private media, credentials, reviewer datasets and generated artifacts
  outside tracked source. Use ignored `data/` for local outputs.
- Choose tests that cover changed behavior. Current frontend tests are not a
  full browser interaction suite.

## Documentation

The [documentation index](docs/README.md) is the entry point. Describe actual
behavior and label planned capabilities explicitly. Preserve historical plans
in `docs/_archive/`; avoid presenting them as current implementation guidance.
The [API reference](docs/API_REFERENCE.md) distinguishes the frontend's demo
API from the separate FastAPI shell.
