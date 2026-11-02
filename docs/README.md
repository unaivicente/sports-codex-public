# Documentation

This documentation describes the implementation inspected on 2 November 2026,
starting from commit `95aed22`. Examples run from the repository root. Source
files and portable schemas are linked throughout so behavior can be checked.

## Start here

| Guide | Purpose |
| --- | --- |
| [Getting started](GETTING_STARTED.md) | Requirements, installation, both servers, configuration, troubleshooting |
| [User guide](USER_GUIDE.md) | Review demo, corrections, dashboard behavior and limitations |
| [Implementation status](STATUS.md) | Capabilities, stubs, integration gaps, verification |
| [Architecture](ARCHITECTURE.md) | Module boundaries, actual data flows, design constraints |
| [Repository structure](REPO_STRUCTURE.md) | Source map and package responsibilities |
| [API reference](API_REFERENCE.md) | Both APIs, routes, bodies, responses and errors |
| [Data contracts](DATA_CONTRACTS.md) | Schemas, provenance, intervals, corrections and training records |
| [Storage](STORAGE.md) | SQLite tables, migrations, seeds, relationship to transport contracts |
| [Model and learning workflows](ML_WORKFLOWS.md) | Extraction, fusion, review scoring, ontology evolution, training preparation, registry, evaluation |
| [Development](DEVELOPMENT.md) | Make targets, CLI flags, tests, builds and contribution workflow |
| [Public access](PUBLIC_ACCESS.md) | Repository and documentation URLs, publication checks, runtime scope |

## Planning documents

- [Project plan](PROJECT_PLAN.md) describes the intended product and learning policy.
- [MVP scope](MVP_SCOPE.md) separates the target MVP from its current delivery.
- [Milestones](MILESTONES.md) maps the roadmap to implementation evidence.
- [Active task note](ACTIVE_TASK.md) explains the historical task brief.
- Files in [`_archive/`](_archive/) preserve original planning documents and are
  historical context rather than the current implementation reference.

Package READMEs provide focused entry points; the root
[contribution guide](../CONTRIBUTING.md) describes project conventions.
