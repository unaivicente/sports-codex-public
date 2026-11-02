"""Timestamp-aligned local frame extraction."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path
import subprocess
from typing import Any, Callable


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


class TimestampConfigError(ValueError):
    """Raised when frame extraction timing settings are invalid."""


class UnsupportedVideoFormatError(ValueError):
    """Raised when a video path is outside the MVP ingestion format."""


class FrameExtractionError(RuntimeError):
    """Raised when a local frame extraction command fails."""


@dataclass(frozen=True)
class ExtractedFrame:
    """Metadata for one extracted frame and its exact video timestamp."""

    frame_index: int
    timestamp: Fraction
    path: Path

    @property
    def timestamp_seconds(self) -> str:
        """Return a stable decimal timestamp for serialization and commands."""

        return format_timestamp_seconds(self.timestamp)

    @property
    def timestamp_numerator(self) -> int:
        return self.timestamp.numerator

    @property
    def timestamp_denominator(self) -> int:
        return self.timestamp.denominator

    def as_metadata(self) -> dict[str, Any]:
        """Return JSON-friendly metadata without losing exact timestamp mapping."""

        return {
            "frame_index": self.frame_index,
            "timestamp_seconds": self.timestamp_seconds,
            "timestamp_numerator": self.timestamp_numerator,
            "timestamp_denominator": self.timestamp_denominator,
            "path": str(self.path),
        }


def plan_frame_timestamps(
    *,
    duration_seconds: int | float | str | Decimal | Fraction,
    fps: int | float | str | Decimal | Fraction,
) -> tuple[Fraction, ...]:
    """Plan start-aligned timestamps for extracting frames at a configured FPS.

    The returned timestamps are exact rational seconds. For example, 3 FPS over
    a one-second interval returns ``0``, ``1/3``, and ``2/3`` rather than rounded
    floating-point values.
    """

    duration = _positive_fraction(duration_seconds, "duration_seconds")
    sample_rate = _positive_fraction(fps, "fps")
    frame_count = _ceil_fraction(duration * sample_rate)

    return tuple(Fraction(frame_index, 1) / sample_rate for frame_index in range(frame_count))


def extract_frames_at_fps(
    video_path: str | Path,
    output_dir: str | Path,
    *,
    fps: int | float | str | Decimal | Fraction,
    duration_seconds: int | float | str | Decimal | Fraction | None = None,
    image_extension: str = ".jpg",
    ffmpeg_path: str = "ffmpeg",
    ffprobe_path: str = "ffprobe",
    runner: CommandRunner | None = None,
) -> tuple[ExtractedFrame, ...]:
    """Extract local MP4 frames at the requested FPS and return timestamp metadata.

    ``duration_seconds`` may be supplied by a caller that already knows the video
    duration. If omitted, the duration is probed locally with ``ffprobe``.
    """

    source = Path(video_path)
    if source.suffix.lower() != ".mp4":
        raise UnsupportedVideoFormatError("MVP ingestion supports local MP4 files only")
    if not source.is_file():
        raise FileNotFoundError(f"video file not found: {source}")

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    command_runner = runner or subprocess.run
    duration = (
        _positive_fraction(duration_seconds, "duration_seconds")
        if duration_seconds is not None
        else probe_video_duration(source, ffprobe_path=ffprobe_path, runner=command_runner)
    )
    timestamps = plan_frame_timestamps(duration_seconds=duration, fps=fps)
    frames = tuple(
        ExtractedFrame(
            frame_index=index,
            timestamp=timestamp,
            path=output_root / f"frame_{index:06d}{_normalized_extension(image_extension)}",
        )
        for index, timestamp in enumerate(timestamps)
    )

    for frame in frames:
        _run_ffmpeg_extract(
            source,
            frame,
            ffmpeg_path=ffmpeg_path,
            runner=command_runner,
        )

    return frames


def probe_video_duration(
    video_path: str | Path,
    *,
    ffprobe_path: str = "ffprobe",
    runner: CommandRunner | None = None,
) -> Fraction:
    """Read local video duration in seconds with ``ffprobe``."""

    command_runner = runner or subprocess.run
    command = [
        ffprobe_path,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    result = _run_command(command_runner, command)
    return _positive_fraction(result.stdout.strip(), "duration_seconds")


def format_timestamp_seconds(timestamp: Fraction) -> str:
    """Format a rational timestamp as a stable decimal seconds string."""

    if timestamp.denominator == 1:
        return str(timestamp.numerator)

    with localcontext() as context:
        context.prec = 28
        text = format(Decimal(timestamp.numerator) / Decimal(timestamp.denominator), "f")

    return text.rstrip("0").rstrip(".")


def _run_ffmpeg_extract(
    video_path: Path,
    frame: ExtractedFrame,
    *,
    ffmpeg_path: str,
    runner: CommandRunner,
) -> None:
    command = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        frame.timestamp_seconds,
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(frame.path),
    ]
    _run_command(runner, command)


def _run_command(runner: CommandRunner, command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return runner(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        executable = command[0]
        raise FrameExtractionError(f"local executable not found: {executable}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        suffix = f": {detail}" if detail else ""
        raise FrameExtractionError(f"local command failed: {' '.join(command)}{suffix}") from exc


def _positive_fraction(value: int | float | str | Decimal | Fraction, name: str) -> Fraction:
    try:
        fraction = _to_fraction(value)
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise TimestampConfigError(f"{name} must be a positive number") from exc

    if fraction <= 0:
        raise TimestampConfigError(f"{name} must be greater than 0")
    return fraction


def _to_fraction(value: int | float | str | Decimal | Fraction) -> Fraction:
    if isinstance(value, Fraction):
        return value
    if isinstance(value, float):
        return Fraction(str(value))
    if isinstance(value, Decimal):
        return Fraction(value)
    return Fraction(value)


def _ceil_fraction(value: Fraction) -> int:
    quotient, remainder = divmod(value.numerator, value.denominator)
    return quotient + (1 if remainder else 0)


def _normalized_extension(extension: str) -> str:
    if not extension:
        raise ValueError("image_extension must not be empty")
    normalized = extension if extension.startswith(".") else f".{extension}"
    if "/" in normalized or "\\" in normalized:
        raise ValueError("image_extension must be a file extension, not a path")
    return normalized
