# Feature implementation plan — video-tool

Status legend: `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked/deferred (reason noted)

Execution order below is chosen by dependency + risk (cheap/independent UI & queue
features first, persistence next, media-processing/ffmpeg-heavy features last since
they are the most expensive to iterate on). Each item has its own subplan with concrete
files touched, and a verification step. After each item: run
`.venv\Scripts\python.exe -m pytest`, `-m ruff check .`, `-m mypy .`,
`-m import_linter` (or `lint-imports`), fix failures, and do a manual/automated smoke
check before moving to the next item. Progress/decisions are logged to
`/memories/repo/video-tool.md` as they happen.

---

## 1. Panel de configuración en la UI [x] DONE
Goal: change `source`/`target` folders and default quality from the UI, persisted
across restarts, without editing `.env` by hand.
- Domain: extend `AppConfig`? Keep `AppConfig` as the env-loaded snapshot; add a new
  `UserPreferences` model (default_quality, last source/target overrides) persisted as
  JSON in a user config dir.
- Application: `application/use_cases/update_preferences.py` (load/save via a new
  `IPreferencesStore` port).
- Infrastructure: `infrastructure/json_preferences_store.py` implementing the port,
  writes to `platformdirs`-less simple path (e.g. `Path.home() / ".video-tool" /
  "preferences.json"`).
- Presentation: settings dialog (gear icon in header) with inputs for source/target
  (folder pickers via `ui.input` + native dialog is out of scope for native window —
  use plain path text input with validation) and default quality radio.
- Test: unit test for the use case + store (tmp_path), manual smoke via browser tools.

## 2. Búsqueda/filtro de videos [x] DONE
Goal: text filter box above the video list.
- Presentation only: add `ui.input` bound to a module-level/state `filter_text`, filter
  the `videos` list in `video_list_panel` by case-insensitive substring match on
  `display_name`.
- Test: unit test not applicable (pure UI); verify manually with browser automation
  (type text, assert filtered DOM).

## 3. Notificación del sistema al terminar un job [x] DONE
Goal: OS-level toast (not just in-page `ui.notify`) when a job finishes, useful when
window unfocused.
- Infrastructure: `infrastructure/os_notifier.py` using `plyer` or Windows-only
  `win10toast`/`winotify`; keep it optional/best-effort (swallow errors, log only).
- Presentation: call from `_on_status_changed` in `main_page.py` when job transitions to
  DONE/ERROR.
- Test: unit test with a fake notifier port (mockable), manual check the balloon
  actually appears on Windows.

## 4. Reintentar job fallido [x] DONE
Goal: "Reintentar" button in `history_panel` for ERROR jobs — re-enqueues same
video+interval as a new PENDING job.
- Presentation + `AppState`: `AppState.retry(job_id)` creates a new `ClipJob` from the
  failed one's video/interval, appends to `jobs`, wakes worker.
- Test: unit test `AppState.retry` in `tests/unit/test_state.py`.

## 5. Pausar/reanudar la cola [x] DONE
Goal: global pause toggle; worker stops picking up new PENDING jobs while paused (does
not interrupt an in-flight job).
- `QueueWorker`: add `paused: bool` + `pause()`/`resume()`, `_next_pending` returns None
  while paused.
- Presentation: toggle button in queue_panel header.
- Test: unit test in `tests/unit/test_queue_worker.py` (pause prevents dequeue, resume
  continues).

## 6. Reordenar la cola [x] DONE
Goal: move a PENDING job up/down in `AppState.jobs` before it's processed.
- `AppState.move_job(job_id, direction)` swaps adjacent PENDING entries only (never
  reorders past a PROCESSING/DONE job).
- Presentation: ↑/↓ buttons per row in `queue_panel`.
- Test: unit test for `move_job`.

## 7. Exportar historial a CSV/JSON [x] DONE
Goal: button to dump `history_panel` entries to a file in `target`.
- Application: `application/use_cases/export_history.py` (pure function: list[ClipJob]
  -> CSV/JSON string), no I/O port needed beyond writing the file (can live in
  infrastructure or be done directly in presentation via `Path.write_text` — keep
  business formatting in application, file write in presentation/infrastructure).
- Test: unit test for the formatting function.

## 8. Carpetas de destino por proyecto (subcarpeta dentro de target) [x] DONE
Goal: optional subfolder field in the clip form; created under `state.config.target`.
- `ClipInterval`: add `subfolder: str | None`.
- `ProcessClipJob`/clipper/audio_extractor: resolve `target / subfolder` if set,
  `mkdir(parents=True, exist_ok=True)`.
- Test: unit + integration test with a subfolder value.

## 9. Presets de recorte guardados [x] DONE
Goal: save current form values (quality, audio_only, subfolder) as a named preset,
reload later.
- Reuses the `IPreferencesStore` from item 1 (`preferences.json` gets a `presets: dict`).
- Presentation: dropdown + "Guardar preset" button in `form_panel`.
- Test: unit test for store round-trip.

## 10. Múltiples recortes por video en un solo envío [x] DONE
Goal: stage several `ClipInterval`s for the same video before enqueuing them all.
- Presentation only: local list in `form_panel` (add to a staging table, "Encolar todos"
  enqueues each via `state.enqueue`).
- Test: manual smoke (adds are pure UI state); consider a small unit test if logic is
  extracted to a plain function (e.g. validate-and-stage).

## 11. Carpeta "watch" (auto-detectar videos nuevos) [x] DONE
Goal: poll `source` periodically and refresh the video list / notify on new files
without manual refresh click.
- Presentation: `ui.timer(interval=3.0, callback=video_list_panel.refresh)` — cheap
  because `VideoRepository` already caches by mtime, so this is just a periodic cheap
  mtime check, consistent with the "no expensive work on frequent callbacks" lesson in
  repo memory.
- Test: manual smoke (add a file to source, confirm it appears without clicking
  refresh).

## 12. Miniaturas (thumbnails) para cada video [x] DONE
Goal: small thumbnail image next to each video name in the list.
- Infrastructure: `infrastructure/moviepy_thumbnailer.py` implementing new
  `IThumbnailer` port (`get_thumbnail(video) -> Path`), extracts a frame at t=1s with
  moviepy, caches under a `.thumbnails/` folder next to target (keyed by video path +
  mtime).
- Presentation: `ui.image(thumb_path)` in `video_list_panel`; generate lazily/async
  (`run.io_bound`) to avoid blocking the event loop.
- Test: integration test using the existing `sample_video` fixture — thumbnail file
  created, is a valid image.

## 13. Preview de video embebido [x] DONE
Goal: `ui.video` player in `form_panel` for the selected video.
- Presentation only: NiceGUI serves local files via `app.add_static_files` or
  `ui.video(video.path.as_uri())` — needs a static route since native mode restricts
  direct filesystem URLs; register `/media` static mount at startup pointing at
  `state.config.source` (read-only).
- Test: manual smoke (browser automation: video element present, correct src).

## 14. Selector visual de intervalo (timeline/scrubber) [x] DONE
Goal: draggable start/end markers rendered over the video preview's duration.
- Depends on 13. Presentation only: custom slider (`ui.range` bound to 0..duration)
  wired to update `start_input`/`end_input` values live; duration read via
  moviepy/ffprobe metadata (small helper in infrastructure, e.g.
  `infrastructure/video_metadata.py::get_duration(path) -> float`).
- Test: unit test for the metadata helper (integration, uses `sample_video`); manual
  smoke for the slider UI.

## 15. Botones "marcar inicio/fin aquí" [x] DONE
Goal: while the preview plays, buttons set start/end inputs to the player's current
time.
- Depends on 13/14. Presentation only: NiceGUI's `ui.video` exposes `on('timeupdate',
  ...)` via JS event / `ui.video.current_time` (may need `run_method`/JS eval — verify
  NiceGUI version capability at implementation time; fallback: poll current time with a
  timer).
- Test: manual smoke via browser automation (play, click mark, assert input value
  changed).

## 16. Fade in/out [x] DONE
Goal: optional audio+video fade at clip boundaries.
- Domain: `ClipInterval.fade_in_seconds: float = 0`, `fade_out_seconds: float = 0`
  (validated >= 0, and `fade_in + fade_out` must not exceed clip duration — validate in
  `ProcessClipJob` or model where duration is known; duration isn't known in the model,
  so validate non-negativity only there and clamp/log in the clipper).
- Infrastructure: `MoviePyClipper.cut` applies
  `.with_effects([vfx.FadeIn(...), vfx.FadeOut(...)])` (moviepy v2 effects API) when set.
- Test: integration test on `sample_video` with fade values, assert success + output
  exists (duration/pixel assertions optional/best-effort).

## 17. Marca de agua / overlay de texto [x] DONE
Goal: optional text overlay (title/watermark) burned into the video.
- Domain: `ClipInterval.watermark_text: str | None`.
- Infrastructure: `MoviePyClipper.cut` composites a `TextClip` (needs ImageMagick or
  moviepy's built-in font rendering — verify availability at implementation time; if
  ImageMagick isn't installed, document as a documented, skippable feature rather than
  blocking the whole plan) over the subclip via `CompositeVideoClip`.
- Test: integration test asserting success; skip/xfail gracefully if the text-rendering
  backend isn't available in this environment (detect and log, don't hard-fail the
  whole suite).

## 18. Subtítulos quemados (burn-in) [x] DONE
Goal: given a `.srt` next to the video (same stem), burn subtitles into the output.
- Infrastructure: use ffmpeg `subtitles` filter directly via moviepy's
  `ffmpeg_params`/subprocess (moviepy doesn't support this natively) —
  `infrastructure/moviepy_clipper.py` shells out to system ffmpeg with the subtitles
  filter as a post-process step, or detect via `ffmpeg_params=["-vf", f"subtitles={srt}"]`
  when supported by the chosen codec path.
- Test: integration test with a tiny synthetic `.srt` fixture; skip gracefully if no
  system ffmpeg with libass support is detected.

## 19. Exportar como GIF [x] DONE
Goal: new output type alongside video/audio.
- Domain: `Quality`/`ClipInterval` gets `output_format` enum extended with `GIF` (or a
  separate `audio_only`-style bool `as_gif`).
- Infrastructure: `MoviePyClipper` branch writes `.gif` via
  `subclip.write_gif(...)` (moviepy v2) when requested.
- Test: integration test on `sample_video`, assert a valid `.gif` file is produced.

## 20. Unir/concatenar varios clips [x] DONE — ALL 20 ITEMS COMPLETE
Goal: combine N existing output clips (or N intervals of possibly different videos)
into a single file.
- Application: new `IConcatenator` port + `application/use_cases/concatenate_clips.py`.
- Infrastructure: `infrastructure/moviepy_concatenator.py` using
  `moviepy.concatenate_videoclips`.
- Presentation: multi-select in `history_panel` ("Unir seleccionados") + a small dialog
  for the output name; enqueues as a new kind of job (extend `ClipJob`/`JobStatus`
  handling or add a parallel `MergeJob` — decide during implementation to minimize
  churn on the existing `ClipJob` FIFO contract).
- Test: integration test merging two `sample_video`-derived clips, assert output
  duration ≈ sum of parts.

---

## Cross-cutting rules while executing this plan
- Never break the Clean Architecture import rules in `AGENTS.md` / `pyproject.toml`
  import-linter contracts — verify with `lint-imports` after each item.
- Every new I/O capability gets an ABC port in `application/ports.py` before an
  infrastructure implementation.
- Every new cross-layer field goes through `domain/models.py` Pydantic models, never
  raw dicts.
- Run the full test suite + ruff + mypy + import-linter after each item; fix before
  moving on. Record any environment-specific skip (e.g. missing ImageMagick/libass) in
  `/memories/repo/video-tool.md` instead of silently ignoring it.
- Update this file's checkboxes as items complete.
