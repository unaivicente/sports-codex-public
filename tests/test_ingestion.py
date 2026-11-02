from __future__ import annotations

from fractions import Fraction
import subprocess
import tempfile
import unittest
from pathlib import Path

from packages.ingestion import (
    FrameExtractionError,
    TimestampConfigError,
    UnsupportedVideoFormatError,
    extract_frames_at_fps,
    format_timestamp_seconds,
    plan_frame_timestamps,
)


class FrameTimestampPlanningTests(unittest.TestCase):
    def test_configurable_fps_controls_timestamp_count_and_spacing(self) -> None:
        self.assertEqual(
            plan_frame_timestamps(duration_seconds=2, fps=2),
            (Fraction(0, 1), Fraction(1, 2), Fraction(1, 1), Fraction(3, 2)),
        )
        self.assertEqual(
            plan_frame_timestamps(duration_seconds=2, fps=4),
            (
                Fraction(0, 1),
                Fraction(1, 4),
                Fraction(1, 2),
                Fraction(3, 4),
                Fraction(1, 1),
                Fraction(5, 4),
                Fraction(3, 2),
                Fraction(7, 4),
            ),
        )

    def test_fractional_timestamps_are_preserved_exactly(self) -> None:
        timestamps = plan_frame_timestamps(duration_seconds=1, fps=3)

        self.assertEqual(timestamps, (Fraction(0, 1), Fraction(1, 3), Fraction(2, 3)))
        self.assertEqual(
            format_timestamp_seconds(timestamps[1]),
            "0.3333333333333333333333333333",
        )

    def test_invalid_timing_configuration_is_rejected(self) -> None:
        with self.assertRaises(TimestampConfigError):
            plan_frame_timestamps(duration_seconds=0, fps=2)

        with self.assertRaises(TimestampConfigError):
            plan_frame_timestamps(duration_seconds=1, fps=0)


class FrameExtractionTests(unittest.TestCase):
    def test_extract_frames_runs_local_ffmpeg_and_returns_exact_timestamp_mapping(self) -> None:
        commands: list[list[str]] = []

        def fake_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video_path = root / "clip.mp4"
            output_dir = root / "frames"
            video_path.write_bytes(b"local fixture")

            frames = extract_frames_at_fps(
                video_path,
                output_dir,
                fps=2,
                duration_seconds=2,
                runner=fake_runner,
            )

        self.assertEqual(len(frames), 4)
        self.assertEqual(
            [frame.timestamp for frame in frames],
            [Fraction(0), Fraction(1, 2), Fraction(1), Fraction(3, 2)],
        )
        self.assertEqual([frame.timestamp_seconds for frame in frames], ["0", "0.5", "1", "1.5"])
        self.assertEqual(frames[1].as_metadata()["timestamp_numerator"], 1)
        self.assertEqual(frames[1].as_metadata()["timestamp_denominator"], 2)
        self.assertEqual([command[0] for command in commands], ["ffmpeg"] * 4)
        self.assertEqual(
            [command[command.index("-ss") + 1] for command in commands],
            ["0", "0.5", "1", "1.5"],
        )

    def test_duration_can_be_probed_locally_when_not_supplied(self) -> None:
        commands: list[list[str]] = []

        def fake_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            if command[0] == "ffprobe":
                return subprocess.CompletedProcess(command, 0, stdout="1.5\n", stderr="")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video_path = root / "clip.mp4"
            video_path.write_bytes(b"local fixture")

            frames = extract_frames_at_fps(video_path, root / "frames", fps=2, runner=fake_runner)

        self.assertEqual(
            [command[0] for command in commands],
            ["ffprobe", "ffmpeg", "ffmpeg", "ffmpeg"],
        )
        self.assertEqual([frame.timestamp for frame in frames], [Fraction(0), Fraction(1, 2), Fraction(1)])

    def test_mvp_rejects_non_mp4_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "clip.mov"
            video_path.write_bytes(b"local fixture")

            with self.assertRaises(UnsupportedVideoFormatError):
                extract_frames_at_fps(
                    video_path,
                    Path(temp_dir) / "frames",
                    fps=1,
                    duration_seconds=1,
                    runner=lambda command, **kwargs: subprocess.CompletedProcess(command, 0),
                )

    def test_local_command_failures_are_wrapped(self) -> None:
        def failing_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            raise subprocess.CalledProcessError(1, command, stderr="decode failed")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video_path = root / "clip.mp4"
            video_path.write_bytes(b"local fixture")

            with self.assertRaises(FrameExtractionError) as context:
                extract_frames_at_fps(
                    video_path,
                    root / "frames",
                    fps=1,
                    duration_seconds=1,
                    runner=failing_runner,
                )

        self.assertIn("decode failed", str(context.exception))


if __name__ == "__main__":
    unittest.main()
