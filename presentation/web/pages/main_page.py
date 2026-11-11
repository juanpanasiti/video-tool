"""Main page — video list (left), clip form (right), and the live processing queue.

A single page replaces the old select → intervals → processing → summary
navigation: accepting a clip enqueues it immediately (FIFO) instead of
collecting a batch first, so clips for different videos can pile up while
earlier ones are still being cut.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Literal

from nicegui import background_tasks, events, run, ui

from application.use_cases.export_history import format_history_csv, format_history_json
from domain.exceptions import (
    NoVideosFoundError,
    SourceFolderNotFoundError,
    TargetFolderNotFoundError,
)
from domain.models import (
    AppConfig,
    ClipInterval,
    ClipJob,
    ClipPreset,
    ClipResult,
    JobStatus,
    Quality,
    VideoFile,
)
from presentation.web.app import get_state, get_worker

logger = logging.getLogger("video_tool.main_page")

_QUALITY_LABELS: dict[Quality, str] = {
    Quality.ORIGINAL: "Original (Sin pérdida / Sin recodificar)",
    Quality.HIGH: "Alta (CRF 18 / 320 kbps)",
    Quality.MEDIUM: "Media (CRF 24 / 192 kbps)",
    Quality.LOW: "Baja (CRF 30 / 128 kbps)",
}
_QUALITY_BY_LABEL = {label: quality for quality, label in _QUALITY_LABELS.items()}

# job.id -> its progress bar widget, refreshed by queue_panel(); updated directly (no
# panel rebuild) on every frame-level tick, since those fire many times per second.
_progress_bars: dict[str, ui.linear_progress] = {}

# job.id of finished, successful jobs checked for "Unir seleccionados" (merge).
_merge_selection: set[str] = set()

# (video path, mtime) -> duration in seconds, or None if it couldn't be read.
# Read via a worker thread, never synchronously.
_duration_cache: dict[tuple[Path, int], float | None] = {}


async def _load_duration(video: VideoFile, cache_key: tuple[Path, int]) -> None:
    try:
        duration = await run.io_bound(get_state().video_metadata.get_duration, video)
    except Exception as exc:
        logger.debug("Duration unavailable for %s: %s", video.display_name, exc)
        duration = None
    _duration_cache[cache_key] = duration
    form_panel.refresh()


def _refresh_all() -> None:
    video_list_panel.refresh()
    form_panel.refresh()
    queue_panel.refresh()
    history_panel.refresh()


def _on_status_changed(job: ClipJob) -> None:
    """Rebuild the panels affected by a job being added/started/finished (rare)."""
    video_list_panel.refresh()
    queue_panel.refresh()
    history_panel.refresh()

    if job.status == JobStatus.DONE:
        get_state().notifier.notify("Clip listo", f"'{job.interval.title}' terminó correctamente.")
    elif job.status == JobStatus.ERROR:
        get_state().notifier.notify("Error al procesar clip", f"'{job.interval.title}' falló.")


def _on_progress(job: ClipJob) -> None:
    """Update a single progress bar's value (cheap; fires many times per second)."""
    bar = _progress_bars.get(job.id)
    if bar is not None:
        bar.set_value(job.progress)


def _open_path(path: Path) -> None:
    if not path.exists():
        ui.notify(f"Archivo no encontrado: {path}", type="negative")
        return
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception as exc:
        ui.notify(str(exc), type="negative")


async def _rename(current_path: Path) -> Path | None:
    """Prompt for a new filename and rename the file in place. Returns the new path, if renamed."""
    with ui.dialog() as dialog, ui.card():
        ui.label("Renombrar archivo").classes("font-bold")
        name_input = ui.input(value=current_path.name).classes("w-full")
        with ui.row().classes("w-full justify-end mt-2"):
            ui.button("Cancelar", on_click=lambda: dialog.submit(None)).props("outline")
            ui.button("Renombrar", on_click=lambda: dialog.submit(name_input.value.strip()))

    new_name = await dialog
    if not new_name or new_name == current_path.name:
        return None
    new_path = current_path.parent / new_name
    try:
        current_path.rename(new_path)
    except OSError as exc:
        ui.notify(f"No se pudo renombrar: {exc}", type="negative")
        return None
    return new_path


def _cancel(job: ClipJob) -> None:
    get_state().cancel(job.id)
    _refresh_all()


async def _open_settings_dialog() -> None:
    """Let the user change source/target folders and the default quality preset."""
    state = get_state()

    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label("Configuración").classes("font-bold text-lg")
        error_label = ui.label("").classes("text-red-500")
        error_label.set_visibility(False)

        source_input = ui.input(label="Carpeta fuente", value=str(state.config.source)).classes(
            "w-full"
        )
        target_input = ui.input(label="Carpeta destino", value=str(state.config.target)).classes(
            "w-full"
        )
        quality_labels = list(_QUALITY_LABELS.values())
        quality_radio = ui.radio(
            quality_labels, value=_QUALITY_LABELS[state.preferences.default_quality]
        )

        with ui.row().classes("w-full justify-end mt-2"):
            ui.button("Cancelar", on_click=lambda: dialog.submit(False)).props("outline")
            ui.button("Guardar", on_click=lambda: dialog.submit(True))

    saved = await dialog
    if not saved:
        return

    try:
        new_config = AppConfig(
            source=Path(source_input.value.strip()),
            target=Path(target_input.value.strip()),
        )
    except (SourceFolderNotFoundError, TargetFolderNotFoundError) as exc:
        ui.notify(str(exc), type="negative")
        return

    state.config = new_config
    state.selected_video = None
    state.preferences.default_quality = _QUALITY_BY_LABEL[quality_radio.value]
    state.preferences.last_source = new_config.source
    state.preferences.last_target = new_config.target
    state.preferences_store.save(state.preferences)

    ui.notify("Configuración guardada", type="positive")
    _refresh_all()


@ui.refreshable
def video_list_panel() -> None:
    state = get_state()

    try:
        videos: list[VideoFile] = state.repository.list_videos(state.config.source)
    except NoVideosFoundError as exc:
        ui.label(f"⚠ {exc}").classes("text-red-500")
        return

    if state.video_filter:
        needle = state.video_filter.lower()
        videos = [v for v in videos if needle in v.display_name.lower()]
        if not videos:
            ui.label(f"(sin resultados para «{state.video_filter}»)").classes("text-gray-500")
            return

    processing_names = state.repository.detect_processing(
        state.config.source, [v.name for v in videos]
    )

    def _select(video: VideoFile) -> None:
        state.selected_video = video
        _refresh_all()

    for video in videos:
        busy = video.name in processing_names or state.is_video_busy(video)
        selected = state.selected_video is not None and state.selected_video.path == video.path
        classes = "w-full items-center px-2 py-1 cursor-pointer hover:bg-white/10 border-b"
        if selected:
            classes += " bg-white/10"
        with ui.row().classes(classes).on("click", lambda _, v=video: _select(v)):
            label = ui.label(f"⚡ {video.display_name}" if busy else video.display_name).classes(
                "flex-grow"
            )
            if busy:
                label.style("color: #d97706")  # amber — externally processing or queued here


@ui.refreshable
def form_panel() -> None:
    state = get_state()
    worker = get_worker()
    video = state.selected_video
    if video is None:
        ui.label("⟵ Seleccioná un video de la lista para definir un recorte.").classes(
            "text-gray-500"
        )
        return

    def _toggle_player(e: events.ValueChangeEventArguments) -> None:
        state.show_player = bool(e.value)
        form_panel.refresh()

    with ui.row().classes("w-full items-center justify-between"):
        ui.label(f"Video: {video.display_name}").classes("text-gray-500")
        ui.switch("Reproductor", value=state.show_player, on_change=_toggle_player)
    video_player = (
        ui.video(str(video.path)).classes("w-full").props("controls") if state.show_player else None
    )

    error_label = ui.label("").classes("text-red-500")
    error_label.set_visibility(False)

    def _show_error(message: str) -> None:
        error_label.text = f"⚠ {message}"
        error_label.set_visibility(True)

    title_input = ui.input(label="Título", placeholder="Nombre del clip").classes("w-full")
    start_input = ui.input(
        label="Inicio", placeholder="0 / 1:30 / 1.30 / 1:01:30 (vacío = inicio)"
    ).classes("w-full")
    end_input = ui.input(
        label="Fin", placeholder="0 / 1:30 / 1.30 / 1:01:30 (vacío = fin)"
    ).classes("w-full")

    async def _current_player_time() -> float:
        if video_player is None:
            return 0.0
        result = await ui.run_javascript(f"getHtmlElement({video_player.id}).currentTime")
        return float(result or 0.0)

    async def _mark_start() -> None:
        start_input.value = str(round(await _current_player_time(), 2))

    async def _mark_end() -> None:
        end_input.value = str(round(await _current_player_time(), 2))

    if video_player is not None:
        with ui.row().classes("w-full gap-2"):
            ui.button("⏱ Marcar inicio aquí", on_click=_mark_start).props("outline dense")
            ui.button("⏱ Marcar fin aquí", on_click=_mark_end).props("outline dense")

    mtime = int(video.path.stat().st_mtime)
    duration_cache_key = (video.path, mtime)
    if duration_cache_key not in _duration_cache:
        ui.label("Cargando duración…").classes("text-gray-500 text-sm")
        background_tasks.create(
            _load_duration(video, duration_cache_key), name=f"duration-{video.path}"
        )
    else:
        duration = _duration_cache[duration_cache_key]
        if duration and duration > 0:

            def _on_range_change(e: events.ValueChangeEventArguments) -> None:
                bounds = e.value or {}
                start_input.value = str(round(bounds.get("min", 0.0), 2))
                end_input.value = str(round(bounds.get("max", duration), 2))

            ui.range(
                min=0, max=duration, value={"min": 0, "max": duration}, on_change=_on_range_change
            ).classes("w-full")
            ui.label(f"Duración: {duration:.1f}s — arrastrá los extremos para ajustar inicio/fin").classes(
                "text-gray-500 text-xs"
            )

    audio_switch = ui.switch("Solo audio (MP3)")
    quality_radio = ui.radio(
        list(_QUALITY_LABELS.values()), value=_QUALITY_LABELS[state.preferences.default_quality]
    )
    subfolder_input = ui.input(
        label="Subcarpeta (opcional)", placeholder="ej. proyecto-x"
    ).classes("w-full")
    with ui.row().classes("w-full gap-2"):
        fade_in_input = ui.number(label="Fade in (s)", value=0, min=0, step=0.5).classes("flex-grow")
        fade_out_input = ui.number(label="Fade out (s)", value=0, min=0, step=0.5).classes("flex-grow")
    watermark_input = ui.input(
        label="Marca de agua (opcional)", placeholder="ej. © Mi Canal"
    ).classes("w-full")
    has_srt = video.path.with_suffix(".srt").exists()
    subtitles_switch = ui.switch(f"Quemar subtítulos ({video.path.with_suffix('.srt').name})")
    if not has_srt:
        subtitles_switch.set_visibility(False)
    gif_switch = ui.switch("Exportar como GIF")

    def _apply_preset(name: str | None) -> None:
        preset = state.preferences.presets.get(name) if name else None
        if preset is None:
            return
        quality_radio.value = _QUALITY_LABELS[preset.quality]
        audio_switch.value = preset.audio_only
        subfolder_input.value = preset.subfolder or ""

    async def _save_preset() -> None:
        with ui.dialog() as dialog, ui.card():
            ui.label("Guardar preset").classes("font-bold")
            name_input = ui.input(label="Nombre del preset").classes("w-full")
            with ui.row().classes("w-full justify-end mt-2"):
                ui.button("Cancelar", on_click=lambda: dialog.submit(None)).props("outline")
                ui.button("Guardar", on_click=lambda: dialog.submit((name_input.value or "").strip()))

        name = await dialog
        if not name:
            return
        state.preferences.presets[name] = ClipPreset(
            quality=_QUALITY_BY_LABEL[quality_radio.value],
            audio_only=bool(audio_switch.value),
            subfolder=(subfolder_input.value or "").strip() or None,
        )
        state.preferences_store.save(state.preferences)
        ui.notify(f"Preset '{name}' guardado", type="positive")
        form_panel.refresh()

    with ui.row().classes("w-full items-center gap-2"):
        ui.select(
            list(state.preferences.presets.keys()),
            label="Preset",
            on_change=lambda e: _apply_preset(e.value),
        ).classes("flex-grow")
        ui.button(icon="save", on_click=_save_preset).props("flat dense").tooltip(
            "Guardar valores actuales como preset"
        )

    def _accept() -> None:
        error_label.set_visibility(False)

        title = (title_input.value or "").strip()
        if not title:
            _show_error("El título es obligatorio.")
            return

        start = (start_input.value or "").strip() or "0"
        end = (end_input.value or "").strip() or None
        quality = _QUALITY_BY_LABEL[quality_radio.value]

        try:
            interval = ClipInterval(
                title=title,
                start=start,
                end=end,
                audio_only=bool(audio_switch.value),
                quality=quality,
                subfolder=(subfolder_input.value or "").strip() or None,
                fade_in_seconds=fade_in_input.value or 0,
                fade_out_seconds=fade_out_input.value or 0,
                watermark_text=(watermark_input.value or "").strip() or None,
                burn_subtitles=bool(subtitles_switch.value),
                as_gif=bool(gif_switch.value),
            )
        except Exception as exc:
            _show_error(str(exc))
            return

        state.stage(video, interval)

        title_input.value = ""
        start_input.value = ""
        end_input.value = ""

        form_panel.refresh()

    ui.button("+ Agregar a la lista", on_click=_accept).props("outline")

    staged = state.staged.get(video.path, [])
    if staged:
        ui.label(f"Recortes por encolar ({len(staged)})").classes("font-bold mt-2")
        for i, staged_interval in enumerate(staged):
            with ui.row().classes("w-full items-center gap-2 px-2 py-1 border-b"):
                label = f"{staged_interval.title}  [{staged_interval.start} → {staged_interval.end or 'fin'}]"
                ui.label(label).classes("flex-grow")
                ui.button(
                    icon="close", on_click=lambda i=i: _unstage(video, i)
                ).props("flat round dense")

        def _enqueue_staged() -> None:
            jobs = state.enqueue_staged(video)
            worker.notify()
            ui.notify(f"{len(jobs)} clip(s) encolados", type="positive")
            _refresh_all()

        ui.button(f"▶ Encolar todos ({len(staged)})", on_click=_enqueue_staged)


def _unstage(video: VideoFile, index: int) -> None:
    get_state().unstage(video, index)
    form_panel.refresh()


@ui.refreshable
def queue_panel() -> None:
    state = get_state()
    worker = get_worker()
    _progress_bars.clear()

    with ui.row().classes("w-full items-center justify-between"):
        ui.label("⏸ Pausada" if worker.paused else "▶ Activa").classes(
            "text-amber-500" if worker.paused else "text-green-500"
        )
        ui.button(
            "▶ Reanudar" if worker.paused else "⏸ Pausar", on_click=lambda: _toggle_pause()
        ).props("outline dense")

    active = [j for j in state.jobs if j.status in (JobStatus.PENDING, JobStatus.PROCESSING)]
    if not active:
        ui.label("(nada en cola)").classes("text-gray-500")
        return

    for job in active:
        with ui.row().classes("w-full items-center gap-2 px-2 py-1 border-b"):
            ui.label("▶" if job.status == JobStatus.PROCESSING else "⏳").classes("w-6")
            with ui.column().classes("flex-grow gap-0"):
                ui.label(f"{job.interval.title}  —  {job.video.display_name}").classes(
                    "font-bold"
                )
                bar = ui.linear_progress(value=job.progress, show_value=False).classes("w-full")
                _progress_bars[job.id] = bar
            if job.status == JobStatus.PENDING:
                ui.button(icon="arrow_upward", on_click=lambda j=job: _move(j, "up")).props(
                    "flat round dense"
                )
                ui.button(icon="arrow_downward", on_click=lambda j=job: _move(j, "down")).props(
                    "flat round dense"
                )
                ui.button("✕ Quitar", on_click=lambda j=job: _cancel(j)).props("outline")


def _move(job: ClipJob, direction: Literal["up", "down"]) -> None:
    if get_state().move_job(job.id, direction):
        queue_panel.refresh()


def _toggle_pause() -> None:
    worker = get_worker()
    if worker.paused:
        worker.resume()
    else:
        worker.pause()
    queue_panel.refresh()


@ui.refreshable
def history_panel() -> None:
    state = get_state()
    finished = [j for j in state.jobs if j.status in (JobStatus.DONE, JobStatus.ERROR)]
    if not finished:
        ui.label("(sin clips terminados todavía)").classes("text-gray-500")
        return

    with ui.row().classes("w-full justify-end gap-2"):
        ui.button("Exportar CSV", on_click=lambda: _export_history("csv")).props(
            "outline dense"
        )
        ui.button("Exportar JSON", on_click=lambda: _export_history("json")).props(
            "outline dense"
        )
        ui.button(
            f"🔗 Unir seleccionados ({len(_merge_selection)})", on_click=_merge_selected
        ).props("outline dense").set_enabled(len(_merge_selection) >= 2)

    for job in reversed(finished):
        result = job.result
        with ui.row().classes("w-full items-center px-2 py-1 border-b"):
            if result is not None and result.success:
                ui.checkbox(
                    value=job.id in _merge_selection,
                    on_change=lambda e, j=job: _toggle_merge_selection(j.id, bool(e.value)),
                )
            with ui.column().classes("flex-grow gap-0"):
                ui.label(f"{job.interval.title}  —  {job.video.display_name}").classes(
                    "font-bold"
                )
                if result is not None and result.success:
                    path_label = ui.label(str(result.output_path)).classes(
                        "text-gray-500 italic"
                    )
                else:
                    error_msg = result.error if result is not None else "Error desconocido"
                    ui.label(f"✖ {error_msg}").classes("text-red-500")
            if result is not None and result.success:
                with ui.row().classes("w-64 justify-end"):

                    async def _handle_rename(j: ClipJob = job, lbl=path_label) -> None:
                        assert j.result is not None
                        renamed = await _rename(j.result.output_path)
                        if renamed is not None:
                            j.result.output_path = renamed
                            lbl.text = str(renamed)

                    ui.button("✎ Renombrar", on_click=_handle_rename).props("outline")
                    ui.button(
                        "⬡ Abrir", on_click=lambda j=job: _open_path(j.result.output_path)
                    ).props("outline")
            elif job.status == JobStatus.ERROR:
                ui.button("↻ Reintentar", on_click=lambda j=job: _retry(j)).props("outline")


def _retry(job: ClipJob) -> None:
    state = get_state()
    if state.retry(job.id) is not None:
        get_worker().notify()
        ui.notify(f"'{job.interval.title}' reencolado", type="positive")
        _refresh_all()


def _toggle_merge_selection(job_id: str, selected: bool) -> None:
    if selected:
        _merge_selection.add(job_id)
    else:
        _merge_selection.discard(job_id)
    history_panel.refresh()


async def _merge_selected() -> None:
    state = get_state()
    selected_jobs = [j for j in state.jobs if j.id in _merge_selection and j.result is not None]
    if len(selected_jobs) < 2:
        ui.notify("Seleccioná al menos 2 clips para unir.", type="warning")
        return

    with ui.dialog() as dialog, ui.card():
        ui.label("Unir clips seleccionados").classes("font-bold")
        ui.label(f"{len(selected_jobs)} clips, en el orden mostrado en el historial.").classes(
            "text-gray-500 text-sm"
        )
        name_input = ui.input(label="Nombre del archivo final").classes("w-full")
        with ui.row().classes("w-full justify-end mt-2"):
            ui.button("Cancelar", on_click=lambda: dialog.submit(None)).props("outline")
            ui.button("Unir", on_click=lambda: dialog.submit((name_input.value or "").strip()))

    title = await dialog
    if not title:
        return

    results = [j.result for j in selected_jobs if isinstance(j.result, ClipResult)]
    if len(results) < 2:
        ui.notify("Solo se pueden unir clips de video (no audio).", type="warning")
        return
    result = await run.io_bound(state.concatenator.concatenate, results, title, state.config.target)
    assert result is not None  # io_bound only returns None if the callback itself does

    if result.success:
        ui.notify(f"Clips unidos en {result.output_path}", type="positive")
        _merge_selection.clear()
        history_panel.refresh()
    else:
        ui.notify(f"No se pudo unir: {result.error}", type="negative")


def _export_history(fmt: Literal["csv", "json"]) -> None:
    state = get_state()
    content = format_history_csv(state.jobs) if fmt == "csv" else format_history_json(state.jobs)

    output_path = state.config.target / f"history.{fmt}"
    try:
        output_path.write_text(content, encoding="utf-8")
    except OSError as exc:
        ui.notify(f"No se pudo exportar: {exc}", type="negative")
        return
    ui.notify(f"Historial exportado a {output_path}", type="positive")


@ui.page("/")
def main_page() -> None:
    state = get_state()

    with ui.row().classes("w-full items-center justify-between"):
        ui.label("🎬 Video Tool").classes("text-2xl font-bold")
        ui.button(icon="settings", on_click=_open_settings_dialog).props(
            "flat round dense"
        ).tooltip("Configuración")
    ui.label(f"Fuente: {state.config.source}   →   Salida: {state.config.target}").classes(
        "text-gray-500"
    )

    # Draggable splitter so the user can resize the video list vs. form/queue columns.
    with ui.splitter(value=25, limits=(15, 60)).classes("w-full mt-2") as splitter:
        with splitter.before:
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Videos").classes("font-bold")
                ui.button(icon="refresh", on_click=video_list_panel.refresh).props(
                    "flat round dense"
                ).tooltip("Actualizar listado")

            def _on_filter_change(e: events.ValueChangeEventArguments) -> None:
                state.video_filter = (e.value or "").strip()
                video_list_panel.refresh()

            ui.input(placeholder="Buscar video…", on_change=_on_filter_change).props(
                "dense clearable"
            ).classes("w-full")
            video_list_panel()

            # Cheap periodic "watch folder": VideoRepository caches by source
            # mtime, so this is just a stat() check unless files actually changed.
            ui.timer(3.0, video_list_panel.refresh)

        with splitter.after, ui.column().classes("w-full gap-2 pl-4"):
            ui.label("Recorte").classes("font-bold")
            form_panel()

            ui.separator().classes("mt-4")

            with ui.tabs().classes("w-full mt-2") as tabs:
                queue_tab = ui.tab("Cola")
                history_tab = ui.tab("Historial")
            with ui.tab_panels(tabs, value=queue_tab).classes("w-full"):
                with ui.tab_panel(queue_tab):
                    queue_panel()
                with ui.tab_panel(history_tab):
                    history_panel()

    worker = get_worker()
    worker.on_status_changed(_on_status_changed)
    worker.on_progress(_on_progress)
