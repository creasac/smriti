#!/usr/bin/env python3
"""Minimal X11 screen recorder with optional webcam and audio."""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

SIZE_PATTERN = re.compile(r"^\d+x\d+$")
REGION_PATTERN = re.compile(r"^(?P<w>\d+)x(?P<h>\d+)\+(?P<x>\d+),(?P<y>\d+)$")


def run_capture(command: list[str]) -> str | None:
    """Return stdout for a command, or None if unavailable/failing."""
    if shutil.which(command[0]) is None:
        return None
    try:
        proc = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except subprocess.CalledProcessError:
        return None
    return proc.stdout.strip()


def detect_screen_size() -> str | None:
    """Best effort screen size detection for active X11 display."""
    xrandr_output = run_capture(["xrandr", "--current"])
    if xrandr_output:
        for line in xrandr_output.splitlines():
            if "*" in line:
                token = line.split()[0]
                if SIZE_PATTERN.match(token):
                    return token

    xdpyinfo_output = run_capture(["xdpyinfo"])
    if xdpyinfo_output:
        match = re.search(r"dimensions:\s+(\d+x\d+)\s+pixels", xdpyinfo_output)
        if match:
            return match.group(1)

    return None


def parse_region(region: str) -> tuple[str, int, int]:
    """Parse region string WIDTHxHEIGHT+X,Y into size and offsets."""
    match = REGION_PATTERN.match(region)
    if not match:
        raise ValueError("Region must match WIDTHxHEIGHT+X,Y (example: 1280x720+100,80)")
    width = match.group("w")
    height = match.group("h")
    offset_x = int(match.group("x"))
    offset_y = int(match.group("y"))
    return f"{width}x{height}", offset_x, offset_y


def get_pulse_sources() -> list[str]:
    output = run_capture(["pactl", "list", "short", "sources"])
    if not output:
        return []
    sources: list[str] = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            sources.append(parts[1])
    return sources


def pick_default_mic_source(sources: list[str]) -> str | None:
    default = run_capture(["pactl", "get-default-source"])
    if default and not default.endswith(".monitor") and default in sources:
        return default

    for source in sources:
        if not source.endswith(".monitor"):
            return source

    return None


def pick_default_desktop_source(sources: list[str]) -> str | None:
    default_sink = run_capture(["pactl", "get-default-sink"])
    if default_sink:
        monitor = f"{default_sink}.monitor"
        if monitor in sources:
            return monitor

    for source in sources:
        if source.endswith(".monitor"):
            return source

    return None


def list_video_devices() -> list[str]:
    return sorted(str(path) for path in Path("/dev").glob("video*"))


def default_output_path() -> Path:
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path.cwd() / f"recording-{timestamp}.mp4"


def has_playable_video_stream(path: Path) -> bool:
    if shutil.which("ffprobe") is None:
        return path.exists() and path.stat().st_size > 0
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "default=nokey=1:noprint_wrappers=1",
            str(path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    return proc.returncode == 0 and "video" in proc.stdout


class WebcamWindowController:
    """Controls an ffplay webcam preview window in window webcam mode."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.process: subprocess.Popen | None = None
        self.title = f"scrnrcdr-webcam-{os.getpid()}-{int(time.time())}"

    def _build_command(self) -> list[str]:
        command = [
            "ffplay",
            "-hide_banner",
            "-loglevel",
            "error",
            "-fflags",
            "nobuffer",
            "-flags",
            "low_delay",
            "-an",
            "-window_title",
            self.title,
            "-left",
            str(self.args.webcam_window_x),
            "-top",
            str(self.args.webcam_window_y),
            "-vf",
            f"scale={self.args.webcam_width}:-1",
            "-f",
            "v4l2",
            "-framerate",
            str(self.args.fps),
            "-i",
            self.args.webcam_device,
        ]
        if self.args.webcam_always_on_top:
            command.insert(1, "-alwaysontop")
        return command

    def _launch(self) -> subprocess.Popen:
        return subprocess.Popen(
            self._build_command(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )

    def start(self) -> None:
        webcam_path = Path(self.args.webcam_device)
        if not webcam_path.exists():
            raise ValueError(f"Webcam device does not exist: {self.args.webcam_device}")

        self.process = self._launch()
        time.sleep(1.0)
        if self.process.poll() is not None:
            message = "Failed to start webcam preview window."
            if self.process.stderr:
                stderr_tail = self.process.stderr.read().strip().splitlines()
                if stderr_tail:
                    message = f"{message} {stderr_tail[-1]}"
            raise ValueError(message)

    def ensure_running(self) -> None:
        if not self.process:
            return
        if self.process.poll() is None:
            return

        # ffplay exits cleanly on Esc/q; relaunch to keep the webcam window active.
        exited_with = self.process.returncode
        if self.process.stderr:
            self.process.stderr.close()
        if exited_with == 0:
            self.process = self._launch()
            time.sleep(0.2)
            if self.process.poll() is not None:
                if self.process.stderr:
                    self.process.stderr.close()
                self.process = None
            return
        self.process = None

    def stop(self) -> None:
        if not self.process:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        if self.process.stderr:
            self.process.stderr.close()


def build_ffmpeg_command(args: argparse.Namespace) -> tuple[list[str], list[str]]:
    cmd: list[str] = ["ffmpeg", "-hide_banner", "-n", "-nostdin"]
    notes: list[str] = []

    if args.region:
        video_size, offset_x, offset_y = parse_region(args.region)
        notes.append(f"capture region: {args.region}")
    else:
        offset_x = 0
        offset_y = 0
        if args.screen_size:
            if not SIZE_PATTERN.match(args.screen_size):
                raise ValueError("--screen-size must match WIDTHxHEIGHT (example: 1920x1080)")
            video_size = args.screen_size
            notes.append(f"screen size: {video_size} (manual)")
        else:
            detected_size = detect_screen_size()
            video_size = detected_size if detected_size else None
            if video_size:
                notes.append(f"screen size: {video_size} (detected)")
            else:
                notes.append("screen size: not detected (ffmpeg default)")

    display_input = f"{args.display}+{offset_x},{offset_y}"
    cmd.extend(["-thread_queue_size", "1024", "-f", "x11grab", "-framerate", str(args.fps)])
    if video_size:
        cmd.extend(["-video_size", video_size])
    cmd.extend(["-i", display_input])
    notes.append(f"display input: {display_input}")

    input_index = 1
    webcam_index: int | None = None
    if args.webcam and args.webcam_mode == "overlay":
        webcam_path = Path(args.webcam_device)
        if not webcam_path.exists():
            raise ValueError(f"Webcam device does not exist: {args.webcam_device}")
        cmd.extend(
            [
                "-thread_queue_size",
                "1024",
                "-f",
                "v4l2",
                "-framerate",
                str(args.fps),
                "-i",
                args.webcam_device,
            ]
        )
        webcam_index = input_index
        input_index += 1
        notes.append(
            f"webcam: {args.webcam_device} overlay={args.webcam_width}px at ({args.webcam_x},{args.webcam_y})"
        )
    elif args.webcam and args.webcam_mode == "window":
        notes.append(
            "webcam: window mode "
            f"device={args.webcam_device} width={args.webcam_width}px start=({args.webcam_window_x},{args.webcam_window_y})"
        )
        if args.webcam_always_on_top:
            notes.append("webcam window: always on top")

    pulse_sources = get_pulse_sources() if (args.mic or args.desktop_audio) else []
    if (args.mic or args.desktop_audio) and not pulse_sources:
        raise ValueError("Could not read PulseAudio/PipeWire sources (is pactl running?)")

    audio_inputs: list[tuple[str, int, str]] = []
    if args.mic:
        mic_source = args.mic_source or pick_default_mic_source(pulse_sources)
        if not mic_source:
            raise ValueError(
                "No microphone source found. Try --mic-source with one from --list-audio-sources."
            )
        if mic_source not in pulse_sources:
            raise ValueError(f"Mic source not found: {mic_source}")
        cmd.extend(["-thread_queue_size", "1024", "-f", "pulse", "-i", mic_source])
        audio_inputs.append(("mic", input_index, mic_source))
        input_index += 1
        notes.append(f"mic source: {mic_source}")

    if args.desktop_audio:
        desktop_source = args.desktop_source or pick_default_desktop_source(pulse_sources)
        if not desktop_source:
            raise ValueError(
                "No desktop monitor source found. Try --desktop-source with one from --list-audio-sources."
            )
        if desktop_source not in pulse_sources:
            raise ValueError(f"Desktop audio source not found: {desktop_source}")
        cmd.extend(["-thread_queue_size", "1024", "-f", "pulse", "-i", desktop_source])
        audio_inputs.append(("desktop", input_index, desktop_source))
        input_index += 1
        notes.append(f"desktop source: {desktop_source}")

    filters: list[str] = []
    if webcam_index is not None:
        filters.append(f"[{webcam_index}:v]scale={args.webcam_width}:-1[cam]")
        filters.append(f"[0:v][cam]overlay=x={args.webcam_x}:y={args.webcam_y}[vout]")
        video_map = "[vout]"
    else:
        video_map = "0:v"

    audio_map: str | None = None
    if len(audio_inputs) == 2:
        first_idx = audio_inputs[0][1]
        second_idx = audio_inputs[1][1]
        filters.append(
            f"[{first_idx}:a][{second_idx}:a]amix=inputs=2:duration=longest:dropout_transition=2[aout]"
        )
        audio_map = "[aout]"
    elif len(audio_inputs) == 1:
        audio_map = f"{audio_inputs[0][1]}:a"

    if filters:
        cmd.extend(["-filter_complex", ";".join(filters)])

    cmd.extend(["-map", video_map])
    if audio_map:
        cmd.extend(["-map", audio_map])

    cmd.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(args.fps),
        ]
    )

    if audio_map:
        cmd.extend(["-c:a", "aac", "-b:a", "128k", "-ac", "2"])
    else:
        cmd.append("-an")

    if args.duration is not None and args.duration > 0:
        cmd.extend(["-t", str(args.duration)])
        notes.append(f"duration: {args.duration}s")

    cmd.extend(["-movflags", "+faststart", str(args.output)])
    notes.append(f"output: {args.output}")
    return cmd, notes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "X11 screen recorder with optional webcam (window/overlay) and optional mic/desktop audio. "
            "Press Ctrl+C to stop."
        )
    )
    parser.add_argument("--output", type=Path, default=None, help="Output path (default: timestamped mp4)")
    parser.add_argument("--fps", type=int, default=30, help="Frames per second (default: 30)")
    parser.add_argument(
        "--display",
        default=os.environ.get("DISPLAY", ":0.0"),
        help="X11 display (default: $DISPLAY or :0.0)",
    )
    parser.add_argument(
        "--screen-size",
        default=None,
        help="Manual screen size WIDTHxHEIGHT (example: 1920x1080)",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="Capture region WIDTHxHEIGHT+X,Y (example: 1280x720+100,80)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        help="Optional auto-stop duration in seconds",
    )
    parser.add_argument(
        "--webcam",
        action="store_true",
        help="Enable webcam (window or overlay depending on --webcam-mode)",
    )
    parser.add_argument(
        "--webcam-mode",
        choices=["window", "overlay"],
        default="window",
        help=(
            "Webcam mode: 'window' for draggable webcam preview window (captured from desktop), "
            "or 'overlay' for ffmpeg composited overlay (default: window)"
        ),
    )
    parser.add_argument(
        "--webcam-device",
        default="/dev/video0",
        help="Webcam device path (default: /dev/video0)",
    )
    parser.add_argument(
        "--webcam-width",
        type=int,
        default=320,
        help="Webcam width in pixels (default: 320)",
    )
    parser.add_argument(
        "--webcam-x",
        default="main_w-overlay_w-20",
        help="Webcam X position expression for ffmpeg overlay filter",
    )
    parser.add_argument(
        "--webcam-y",
        default="main_h-overlay_h-20",
        help="Webcam Y position expression for ffmpeg overlay filter",
    )
    parser.add_argument(
        "--webcam-window-x",
        type=int,
        default=20,
        help="Initial webcam window X position in pixels (window mode)",
    )
    parser.add_argument(
        "--webcam-window-y",
        type=int,
        default=20,
        help="Initial webcam window Y position in pixels (window mode)",
    )
    parser.add_argument(
        "--webcam-always-on-top",
        action="store_true",
        help="Keep webcam preview window above other windows (window mode)",
    )
    parser.add_argument("--mic", action="store_true", help="Enable microphone capture")
    parser.add_argument(
        "--desktop-audio",
        action="store_true",
        help="Enable desktop/system audio capture",
    )
    parser.add_argument("--mic-source", default=None, help="Manual Pulse source name for mic")
    parser.add_argument(
        "--desktop-source",
        default=None,
        help="Manual Pulse source name for desktop/system audio",
    )
    parser.add_argument(
        "--list-audio-sources",
        action="store_true",
        help="Print Pulse sources and exit",
    )
    parser.add_argument(
        "--list-video-devices",
        action="store_true",
        help="Print /dev/video* devices and exit",
    )
    parser.add_argument(
        "--show-command",
        action="store_true",
        help="Print generated ffmpeg command before recording",
    )
    return parser.parse_args()


def print_lists_and_exit(args: argparse.Namespace) -> bool:
    did_print = False
    if args.list_audio_sources:
        did_print = True
        sources = get_pulse_sources()
        if sources:
            print("Audio sources:")
            for source in sources:
                print(f"  - {source}")
        else:
            print("No audio sources found (check pactl / PulseAudio / PipeWire).")

    if args.list_video_devices:
        did_print = True
        devices = list_video_devices()
        if devices:
            print("Video devices:")
            for device in devices:
                print(f"  - {device}")
        else:
            print("No /dev/video* devices found.")

    return did_print


def run_recording(
    command: list[str],
    notes: list[str],
    show_command: bool,
    output_path: Path,
    webcam_controller: WebcamWindowController | None = None,
) -> int:
    print("Recorder configuration:", flush=True)
    for note in notes:
        print(f"  - {note}", flush=True)

    if show_command:
        print("\nffmpeg command:", flush=True)
        print(shlex.join(command), flush=True)

    if webcam_controller:
        try:
            webcam_controller.start()
        except ValueError as err:
            print(f"Configuration error: {err}", file=sys.stderr)
            return 1
        print(
            "Webcam window mode: drag the webcam window with mouse. "
            "Press Ctrl+C in this terminal to stop recording.",
            flush=True,
        )

    print("\nRecording started. Press Ctrl+C to stop.\n", flush=True)
    interrupted = False
    process = subprocess.Popen(command)
    return_code: int | None = None

    try:
        while True:
            try:
                return_code = process.wait(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                if webcam_controller:
                    webcam_controller.ensure_running()
    except KeyboardInterrupt:
        interrupted = True
        print("\nStopping recording gracefully. Please wait...", flush=True)
        process.send_signal(signal.SIGINT)
        try:
            process.wait()
        except KeyboardInterrupt:
            print("Force stopping recording...", flush=True)
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
    finally:
        if webcam_controller:
            webcam_controller.stop()

    if return_code is None:
        return_code = process.returncode
    if return_code is None:
        return_code = 1

    if interrupted and return_code in (0, 130, 255):
        return_code = 0

    if return_code == 0:
        if not has_playable_video_stream(output_path):
            print(
                (
                    "Recording finished but output has no playable video stream. "
                    "This usually means recording was force-stopped before finalization."
                ),
                file=sys.stderr,
            )
            return 1
        print(f"Saved recording: {output_path}", flush=True)
        return 0
    return return_code


def main() -> int:
    args = parse_args()

    if print_lists_and_exit(args):
        return 0

    if shutil.which("ffmpeg") is None:
        print("ffmpeg is required but not installed or not in PATH.", file=sys.stderr)
        return 1
    if args.webcam and args.webcam_mode == "window" and shutil.which("ffplay") is None:
        print("ffplay is required for --webcam-mode window but is not installed or not in PATH.", file=sys.stderr)
        return 1

    args.output = args.output.expanduser() if args.output else default_output_path()
    if args.output.exists():
        print(f"Output file already exists: {args.output}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)

    if args.fps <= 0:
        print("--fps must be greater than zero.", file=sys.stderr)
        return 1
    if args.webcam_width <= 0:
        print("--webcam-width must be greater than zero.", file=sys.stderr)
        return 1
    if args.webcam and not Path(args.webcam_device).exists():
        print(f"Webcam device does not exist: {args.webcam_device}", file=sys.stderr)
        return 1

    try:
        command, notes = build_ffmpeg_command(args)
    except ValueError as err:
        print(f"Configuration error: {err}", file=sys.stderr)
        return 1

    webcam_controller = None
    if args.webcam and args.webcam_mode == "window":
        webcam_controller = WebcamWindowController(args)

    return run_recording(
        command,
        notes,
        args.show_command,
        output_path=args.output,
        webcam_controller=webcam_controller,
    )


if __name__ == "__main__":
    raise SystemExit(main())
