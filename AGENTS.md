# AI Agent Directives — video-tool

This document defines the architectural constraints, conventions, and guidelines
that AI coding agents MUST follow when working on this codebase.

---

## Architecture: Clean Architecture

This project follows **Clean Architecture** (Uncle Bob). The dependency rule is strict:
> Source code dependencies MUST point **inward only**.
> Inner layers know nothing about outer layers.

```
Domain ← Application ← Infrastructure
                     ← Presentation
```

### Layer Responsibilities

| Layer | Package | Allowed imports |
|-------|---------|-----------------|
| **Domain** | `domain/` | Standard library only. No third-party, no other project packages. |
| **Application** | `application/` | `domain/` and standard library only. No infrastructure, no presentation, no frameworks. |
| **Infrastructure** | `infrastructure/` | `domain/`, `application/ports.py`, and third-party libraries (moviepy, python-dotenv, etc.). |
| **Presentation** | `presentation/` | `domain/`, `application/`, and UI libraries (rich, questionary). |
| **Entry point** | `main.py` | Wires all layers together. This is the only place allowed to import from all layers simultaneously. |

---

## Strict Rules

1. **Never import infrastructure in domain or application.**
   - `domain/` and `application/` MUST NOT import from `infrastructure/` or `presentation/`.
   - Violations break the dependency rule and must be refactored immediately.

2. **Use cases depend only on abstract ports (interfaces), never on concrete implementations.**
   - All I/O operations (file system, video processing) are abstracted via ABC classes in `application/ports.py`.
   - Concrete implementations live in `infrastructure/`.

3. **All data crossing layer boundaries must be Pydantic models (DTOs).**
   - Define models in `domain/models.py`.
   - Use Pydantic `BaseModel` for validation and serialization.
   - Do NOT pass raw dicts or untyped primitives between layers.

4. **Domain layer is pure.**
   - No I/O, no network, no file system access.
   - No framework imports (no pydantic-settings, no dotenv, no moviepy).
   - Domain models define the business concepts; they contain validation logic only.

5. **Exceptions are domain-owned.**
   - All domain-level errors are defined in `domain/exceptions.py`.
   - Infrastructure and presentation layers may catch and re-wrap them, but must not define domain concepts.

6. **No business logic in the presentation or infrastructure layers.**
   - Presentation formats and displays data; it does not decide what to do.
   - Infrastructure performs I/O; it does not enforce business rules.

---

## DTOs and Models (`domain/models.py`)

- `AppConfig` — validated app configuration loaded from environment variables.
- `VideoFile` — represents a discovered video file (name, path, extension).
- `ClipInterval` — represents a single clip request (start time, end time, title).
- `ClipResult` / `AudioResult` — outcome of a clip/audio operation (output path, success, error).
- `JobStatus` / `ClipJob` — lifecycle state of a clip request queued for background processing.

All models use Pydantic v2 `BaseModel`. Use `model_validator` for cross-field validation (e.g., end > start).

---

## Ports (`application/ports.py`)

Abstract base classes (ABCs) defining I/O contracts:

- `IVideoRepository` — `list_videos(source: Path) -> list[VideoFile]`
- `IClipper` — `cut(video, interval, target, on_progress) -> ClipResult`
- `IAudioExtractor` — `extract(video, interval, target) -> AudioResult`

---

## Naming Conventions

- Files and modules: `snake_case`
- Classes: `PascalCase`
- Port (interface) classes: prefix with `I` (e.g., `IClipper`)
- Use case classes: descriptive verb+noun (e.g., `ProcessClipJob`)
- All code, comments, docstrings, and variable names: **English only**

---

## Testing Strategy

- **Unit tests** (`tests/unit/`): test domain models and use cases in isolation. Mock all ports via `pytest-mock`.
- **Integration tests** (`tests/integration/`): wire real infrastructure implementations together using temp directories. `tests/integration/conftest.py::sample_video` generates a tiny synthetic video with moviepy so clipper/audio-extractor tests run a real ffmpeg encode/decode without committing binary fixtures.
- Tests MUST NOT call real external services or modify files outside of `tmp_path`.
- One test file per module tested (e.g., `test_process_clip_job.py` tests `application/use_cases/process_clip_job.py`).
- Run with `uv run pytest` (or, if that hits the local `uv run` rebuild/file-lock issue, `.venv\Scripts\python.exe -m pytest` directly).

---

## Project Structure (reference)

```
video-tool/
├── .env.example
├── AGENTS.md
├── pyproject.toml
├── main.py
├── domain/
│   ├── __init__.py
│   ├── models.py
│   └── exceptions.py
├── application/
│   ├── __init__.py
│   ├── ports.py
│   └── use_cases/
│       ├── __init__.py
│       └── process_clip_job.py
├── infrastructure/
│   ├── __init__.py
│   ├── video_repository.py
│   ├── moviepy_clipper.py
│   └── moviepy_audio_extractor.py
├── presentation/
│   ├── __init__.py
│   └── web/
│       ├── __init__.py
│       ├── app.py          # wires infrastructure into AppState/QueueWorker, launches ui.run(native=True)
│       ├── state.py        # shared state (AppState) incl. the ClipJob FIFO queue
│       ├── queue_worker.py # QueueWorker — background asyncio task draining the job queue one at a time
│       └── pages/
│           ├── __init__.py
│           └── main_page.py  # single page: video list + clip form + queue/history tabs
└── tests/
    ├── unit/
    └── integration/
```

## UI Framework

The presentation layer is a **NiceGUI** app running as a native desktop window
(`ui.run(native=True)`, backed by pywebview). It is a single page
(`presentation/web/pages/main_page.py`) split into a video list, a clip form,
and a live queue/history view built with `@ui.refreshable` sections. Accepting
a clip in the form calls `AppState.enqueue()` and appends a `ClipJob`
(`domain/models.py`) to a single FIFO queue shared by every video — clips for
different videos can be queued while earlier ones are still processing.

A background `QueueWorker` (`presentation/web/queue_worker.py`), started as an
asyncio task from `app.on_startup` in `presentation/web/app.py::run()`, drains
the queue one job at a time via `application/use_cases/process_clip_job.py::ProcessClipJob`,
running the actual cut/extract on a worker thread through `nicegui.run.io_bound`.
Progress callbacks from that thread are marshalled back onto the event loop
with `asyncio.loop.call_soon_threadsafe`, then the worker calls its
`on_job_changed` callback so the UI refreshes the relevant panels.

