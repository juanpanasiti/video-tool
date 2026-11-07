"""Domain-level exceptions for video-tool."""


class VideoToolError(Exception):
    """Base exception for all video-tool domain errors."""


class InvalidTimeFormatError(VideoToolError):
    """Raised when a time string does not match HH:MM:SS or MM:SS format."""

    def __init__(self, value: str) -> None:
        super().__init__(
            f"Invalid time format '{value}'. Expected HH:MM:SS or MM:SS."
        )


class InvalidIntervalError(VideoToolError):
    """Raised when the end time is not strictly after the start time."""

    def __init__(self, start: str, end: str) -> None:
        super().__init__(
            f"End time '{end}' must be greater than start time '{start}'."
        )


class InvalidSubfolderError(VideoToolError):
    """Raised when a requested output subfolder name is unsafe or invalid."""

    def __init__(self, value: str) -> None:
        super().__init__(
            f"Invalid subfolder name '{value}'. It must not contain path separators or be '..'."
        )


class ConflictingOutputModeError(VideoToolError):
    """Raised when mutually exclusive output modes (e.g. audio + GIF) are both requested."""

    def __init__(self) -> None:
        super().__init__("A clip cannot be both audio-only and a GIF — choose one output mode.")


class SourceFolderNotFoundError(VideoToolError):
    """Raised when the SOURCE folder does not exist."""

    def __init__(self, path: str) -> None:
        super().__init__(f"SOURCE folder does not exist: '{path}'")


class TargetFolderNotFoundError(VideoToolError):
    """Raised when the TARGET folder does not exist."""

    def __init__(self, path: str) -> None:
        super().__init__(f"TARGET folder does not exist: '{path}'")


class NoVideosFoundError(VideoToolError):
    """Raised when no supported video files are found in the SOURCE folder."""

    def __init__(self, path: str) -> None:
        super().__init__(f"No video files found in SOURCE folder: '{path}'")


class ClipProcessingError(VideoToolError):
    """Raised when a clip cannot be generated."""

    def __init__(self, title: str, reason: str) -> None:
        super().__init__(f"Failed to process clip '{title}': {reason}")
