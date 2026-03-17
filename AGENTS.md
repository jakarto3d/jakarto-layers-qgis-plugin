# AGENTS.md

## Purpose

This repository is a QGIS plugin for browsing, loading, editing, and syncing Jakarto real-time layers with Supabase and Jakartowns.

Agents working here should optimize for correctness in a QGIS plugin environment first. Small UI or data-flow changes can break signal wiring, object lifetime, or QGIS-version compatibility.

## Ground Truth

- Language/runtime: Python 3.9 target, QGIS plugin, PyQt5, pytest with `pytest-qgis`.
- Minimum supported QGIS version: 3.22 (`jakarto_layers_qgis/metadata.txt`).
- Geometry support is currently point-only. Several modules explicitly reject non-point geometry.
- The repo may be used directly as a QGIS plugin path during development via `QGIS_PLUGINPATH=$(pwd)`.

## Primary Workflow

Use the `justfile` instead of inventing ad hoc commands.

- Create dev environment: `just venv`
- Run tests: `just test`
- Run coverage: `just coverage`
- Format and lint: `just format`
- Launch QGIS against this checkout: `just run-qgis`
- Launch QGIS against local Supabase: `just run-qgis-local-supabase`
- Refresh vendored dependencies: `just vendorize`
- Build plugin zip: `just package`
- Bump release version: `just bump-version <part>`

## Repository Layout

- `jakarto_layers_qgis/__init__.py`: QGIS plugin entry point via `classFactory`; initializes Sentry outside dev mode.
- `jakarto_layers_qgis/plugin.py`: top-level plugin UI, toolbar/menu/browser integration, auth bootstrapping, user actions.
- `jakarto_layers_qgis/adapter.py`: core orchestration layer between QGIS edits, PostgREST writes, and realtime events.
- `jakarto_layers_qgis/layer.py`: in-memory layer model, QGIS signal handling, feature ID mapping, echo suppression.
- `jakarto_layers_qgis/converters.py`: QGIS <-> Supabase feature/layer conversion.
- `jakarto_layers_qgis/supabase_postgrest.py`: REST client for layers/features/RPCs.
- `jakarto_layers_qgis/supabase_realtime_worker.py`: realtime worker living on a `QThread`.
- `jakarto_layers_qgis/presence.py`: Jakartowns presence handling and follow behavior.
- `jakarto_layers_qgis/ui/`: browser-tree integration, dialogs, icons.
- `tests/`: pytest coverage, mostly with mocked network responses and QGIS fixtures.
- `vendoring-patches/`: patches applied to vendored libraries.

## Architecture Notes

- The plugin splits sync responsibilities:
  - QGIS-originated edits go through `Layer` commit signals into `Adapter._commit_callback()`, then to PostgREST.
  - Server-originated updates come through realtime messages handled by `RealTimeWorker`, then `Adapter.on_supabase_realtime_event()`, then into `Layer.on_realtime_*()`.
- `Layer` owns the mapping between QGIS feature IDs and Supabase feature IDs. Preserve this carefully whenever you change insert/update/delete flows.
- Echo suppression is essential. The plugin intentionally ignores events that are reflections of its own writes.
- Temporary layers are used for "Edit in Jakartowns" sync. They are treated differently from persistent real-time layers.
- Realtime runs across Qt threading and asyncio. Avoid introducing blocking work or unsafe cross-thread object access.

## Repo-Specific Rules

- Preserve Python 3.9 compatibility. Do not introduce `match`, `str | None`, or other newer-only syntax.
- Do not expand geometry support casually. Point-only assumptions exist in converters, layer creation, tests, UI text, and metadata.
- Avoid direct edits under `jakarto_layers_qgis/vendor/`. Change `requirements-vendor.txt` and rerun `just vendorize`; keep any necessary patching in `vendoring-patches/`.
- Keep `requirements.txt` limited to packages expected to already exist in the QGIS Python environment. Third-party runtime deps belong in `requirements-vendor.txt`.
- If you change the release version, keep these in sync:
  - `jakarto_layers_qgis/__init__.py`
  - `jakarto_layers_qgis/metadata.txt`
  - `.bumpversion.cfg`
- Prefer the existing logging path in `jakarto_layers_qgis/messages.py`. Do not leave stray `print()` debugging in plugin code.
- Be careful with Qt/QGIS object lifetime. This code already uses `sip.isdeleted`, explicit signal bookkeeping, and delayed cleanup for a reason.

## Auth, Env, and External Services

- Authentication is handled by `JakartoAuthentication`.
- Preferred credential storage is the QGIS auth database; fallback storage is QSettings in clear text.
- Relevant environment variables:
  - `JAKARTO_LAYERS_VERBOSE=1`: enable debug prints routed through `messages.debug()`
  - `JAKARTO_LAYERS_SUPABASE_LOCAL=1`: use local Supabase endpoints
  - `JAKARTO_LAYERS_JAKARTOWNS_URL=...`: override Jakartowns base URL
  - `JAKARTO_VERIFY_SSL=false`: disable SSL verification and patch realtime SSL behavior

## Testing Expectations

- Start with targeted `pytest` runs through `just test`, then broaden if the change touches shared flow.
- Tests rely on QGIS bindings and `pytest-qgis`; they are not plain unit tests.
- The standard suite mocks network responses from files in `tests/responses/`.
- If you touch QGIS-version-sensitive behavior, packaging, or Python-3.9 compatibility, consider `just test-docker` for the QGIS 3.22 / Python 3.9 path.
- When changing import/sync/realtime behavior, verify both directions:
  - QGIS edit -> PostgREST request
  - Supabase realtime event -> QGIS layer mutation

## Safe Change Strategy

Before editing:

- Check `git status` and do not overwrite unrelated user changes.
- Read the touched flow end-to-end. In this repo, "small" edits often cross `plugin.py`, `adapter.py`, `layer.py`, and tests.

Before finishing:

- Run formatting/linting with `just format` when code changed.
- Run the most relevant tests.
- If behavior or supported workflow changed, update `README.md` and/or `jakarto_layers_qgis/metadata.txt` when appropriate.
