from __future__ import annotations

import datetime as dt
import re
import shutil
import subprocess
from pathlib import Path

SIZE_PATTERN = re.compile(r"^\d+x\d+$")


def run_capture(command: list[str]) -> str | None:
    """Return stdout for a command, or None if unavailable or failing."""
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
    """Best effort screen size detection for the active X11 display."""
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


def default_output_path() -> Path:
    timestamp = dt.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    return Path.home() / "Videos" / "smriti" / f"rec-{timestamp}.mp4"


def next_available_output_path() -> Path:
    base = default_output_path()
    if not base.exists():
        return base

    stem = base.stem
    suffix = base.suffix
    counter = 2
    while True:
        candidate = base.with_name(f"{stem}-{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def has_playable_video_stream(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    if shutil.which("ffprobe") is None:
        return True
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


def quote_concat_path(path: Path) -> str:
    return str(path).replace("'", r"'\''")


def read_pipe(pipe: object) -> str:
    if pipe is None:
        return ""
    try:
        return pipe.read().strip()
    except ValueError:
        return ""


def summarize_error(prefix: str, stderr_output: str) -> str:
    lines = [line.strip() for line in stderr_output.splitlines() if line.strip()]
    if not lines:
        return prefix
    return f"{prefix} {lines[-1]}"
