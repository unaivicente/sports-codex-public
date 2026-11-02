# Review web app

React 19, TypeScript, Vite 8 and Vitest application for the local review demo.
From the repository root:

```sh
npm --prefix apps/web ci
npm --prefix apps/web run dev -- --host 127.0.0.1
npm --prefix apps/web test
npm --prefix apps/web run build
```

Start `python -m apps.api.server --host 127.0.0.1 --port 8000` separately.
The default API base URL is `http://127.0.0.1:8000`; override it with
`VITE_API_BASE_URL` or `apps/web/.env.local`. The app expects unversioned demo
API paths and response shapes, not the separate FastAPI shell.

Implemented: browser-local video preview, upload acknowledgement, backend
status, football/basketball selectors, requested mock predictions, timeline,
confirm/relabel form and fixture feedback-quality dashboard. Uploads and
corrections are not persisted; dashboard statistics do not reflect submissions.
The demo-video button creates fixture text rather than a playable MP4.

The build writes `dist/`; `npm --prefix apps/web run preview` serves it locally.
Tests cover contract fixtures and server-rendered dashboard sections, not all
browser interactions. See [user guide](../../docs/USER_GUIDE.md),
[setup](../../docs/GETTING_STARTED.md) and
[API reference](../../docs/API_REFERENCE.md).
