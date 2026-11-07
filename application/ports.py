"""Abstract ports (interfaces) for the application layer.

Use cases depend ONLY on these abstractions.
Concrete implementations live in the infrastructure/ package.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from pathlib import Path

from domain.models import AudioResult, ClipInterval, ClipResult, UserPreferences, VideoFile


class IVideoRepository(ABC):
    """Port for discovering video files in the source folder."""

    @abstractmethod
    def list_videos(self, source: Path) -> list[VideoFile]:
        """Return all supported video files found in *source*.

        Raises:
            NoVideosFoundError: if no video files are present.
        """

    @abstractmethod
    def detect_processing(self, search_dir: Path, candidate_names: Iterable[str]) -> frozenset[str]:
        """Return the subset of *candidate_names* currently being processed externally.

        A name is considered "processing" when a matching moviepy temp file is
        found in *search_dir* (see infrastructure implementation for details).
        """


class IClipper(ABC):
    """Port for cutting a video file into a clip."""

    @abstractmethod
    def cut(
        self,
        video: VideoFile,
        interval: ClipInterval,
        target: Path,
        on_progress: Callable[[float, float], None] | None = None,
    ) -> ClipResult:
        """Cut *video* according to *interval* and write the result to *target*.

        *on_progress* is called with ``(current, total)`` as frames are encoded.
        The output filename is: ``<video.name> - <interval.title><video.extension>``
        """


class IAudioExtractor(ABC):
    """Port for extracting audio from a video file as MP3."""

    @abstractmethod
    def extract(
        self,
        video: VideoFile,
        interval: ClipInterval,
        target: Path,
    ) -> AudioResult:
        """Extract audio from *video* within *interval* and write an MP3 to *target*.

        Output filename: ``<video.name> - <interval.title>.mp3``
        """


class IPreferencesStore(ABC):
    """Port for persisting user preferences across application restarts."""

    @abstractmethod
    def load(self) -> UserPreferences:
        """Return stored preferences, or defaults if none/corrupt are found."""

    @abstractmethod
    def save(self, preferences: UserPreferences) -> None:
        """Persist *preferences* for the next run."""


class INotifier(ABC):
    """Port for sending OS-level desktop notifications (best-effort)."""

    @abstractmethod
    def notify(self, title: str, message: str) -> None:
        """Show a desktop notification. Implementations must not raise on failure."""


class IThumbnailer(ABC):
    """Port for generating a small preview image for a video file."""

    @abstractmethod
    def get_thumbnail(self, video: VideoFile, cache_dir: Path) -> Path:
        """Return the path to a cached thumbnail for *video*.

        Generates and caches it under *cache_dir* (keyed by path + mtime) if
        missing or stale. May raise if the video can't be decoded — callers
        should treat thumbnail generation as best-effort.
        """


class IVideoMetadata(ABC):
    """Port for reading lightweight metadata (no frame decoding) from a video file."""

    @abstractmethod
    def get_duration(self, video: VideoFile) -> float:
        """Return the duration of *video* in seconds. May raise if unreadable."""


class IConcatenator(ABC):
    """Port for joining several already-cut clips into a single output file."""

    @abstractmethod
    def concatenate(self, clips: list[ClipResult], title: str, target: Path) -> ClipResult:
        """Concatenate the (successful) *clips*, in order, into one file under *target*.

        Output filename: ``<sanitized title><extension of the first clip>``
        """

