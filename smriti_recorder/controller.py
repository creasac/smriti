from __future__ import annotations

import queue
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import asdict
from pathlib import Path

from .config import ActiveSegment, AppConfig, ControllerState, RecordingSession
from .system import (
    detect_screen_size,
    get_pulse_sources,
    has_playable_video_stream,
    next_available_output_path,
    pick_default_desktop_source,
    pick_default_mic_source,
    quote_concat_path,
    read_pipe,
    reveal_in_file_manager,
    summarize_error,
)


class WebcamWindowController:
    """Controls the live webcam preview window."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.process: subprocess.Popen[str] | None = None
        self.title = ""

    def _video_filter(self) -> str:
        filters = [f"scale={self.config.webcam_width}:-1"]
        if self.config.webcam_flip_horizontal:
            filters.insert(0, "hflip")
        return ",".join(filters)

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
            str(self.config.webcam_window_x),
            "-top",
            str(self.config.webcam_window_y),
            "-vf",
            self._video_filter(),
            "-f",
            "v4l2",
            "-framerate",
            str(self.config.fps),
            "-i",
            self.config.webcam_device,
        ]
        if self.config.webcam_always_on_top:
            command.insert(1, "-alwaysontop")
        return command

    def _launch(self) -> subprocess.Popen[str]:
        return subprocess.Popen(
            self._build_command(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )

    def start(self) -> None:
        webcam_path = Path(self.config.webcam_device)
        if not webcam_path.exists():
            raise RuntimeError(f"Webcam device does not exist: {self.config.webcam_device}")
        if shutil.which("ffplay") is None:
            raise RuntimeError("ffplay is not installed or not in PATH.")

        self.process = self._launch()
        time.sleep(0.8)
        if self.process.poll() is not None:
            stderr_output = read_pipe(self.process.stderr)
            self.process = None
            raise RuntimeError(summarize_error("Failed to start webcam preview.", stderr_output))

    def ensure_running(self) -> bool:
        if not self.process:
            return False
        if self.process.poll() is None:
            return True

        if self.process.stderr:
            self.process.stderr.close()
        self.process = None
        return False

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
        self.process = None


def resolve_audio_sources(mic_enabled: bool) -> tuple[str | None, str | None, list[str]]:
    sources = get_pulse_sources()
    warnings: list[str] = []

    desktop_source = pick_default_desktop_source(sources)
    if not desktop_source:
        warnings.append("Desktop audio unavailable; recording silence instead.")

    mic_source = None
    if mic_enabled:
        mic_source = pick_default_mic_source(sources)
        if not mic_source:
            warnings.append("Microphone unavailable; continuing without mic.")

    return desktop_source, mic_source, warnings


def build_segment_command(
    config: AppConfig,
    output_path: Path,
    mic_enabled: bool,
) -> tuple[list[str], list[str]]:
    command: list[str] = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-nostdin",
        "-thread_queue_size",
        "1024",
        "-f",
        "x11grab",
        "-framerate",
        str(config.fps),
    ]

    screen_size = detect_screen_size()
    if screen_size:
        command.extend(["-video_size", screen_size])

    command.extend(["-i", f"{config.display}+0,0"])

    desktop_source, mic_source, warnings = resolve_audio_sources(mic_enabled)

    input_index = 1
    desktop_index: int | None = None
    if desktop_source:
        command.extend(["-thread_queue_size", "1024", "-f", "pulse", "-i", desktop_source])
        desktop_index = input_index
        input_index += 1

    mic_index: int | None = None
    if mic_source:
        command.extend(["-thread_queue_size", "1024", "-f", "pulse", "-i", mic_source])
        mic_index = input_index
        input_index += 1

    audio_inputs: list[str] = []
    if desktop_index is not None:
        audio_inputs.append(f"[{desktop_index}:a]")
    if mic_index is not None:
        audio_inputs.append(f"[{mic_index}:a]")

    if not audio_inputs:
        command.extend(["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"])
        audio_inputs.append(f"[{input_index}:a]")

    if len(audio_inputs) == 1:
        audio_filter = (
            f"{audio_inputs[0]}aformat=sample_fmts=fltp:sample_rates=48000:"
            "channel_layouts=stereo[aout]"
        )
    else:
        audio_filter = (
            "".join(audio_inputs)
            + f"amix=inputs={len(audio_inputs)}:duration=longest:dropout_transition=0:normalize=0,"
            "aresample=async=1:first_pts=0,"
            "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[aout]"
        )

    command.extend(
        [
            "-filter_complex",
            audio_filter,
            "-map",
            "0:v",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(config.fps),
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-ac",
            "2",
            "-ar",
            "48000",
            str(output_path),
        ]
    )

    return command, warnings


class RecorderController:
    """Serializes recorder operations off the UI thread."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.state = ControllerState(
            status="Checking environment...",
            webcam_enabled=config.default_webcam_enabled,
            webcam_flipped=config.webcam_flip_horizontal,
            mic_enabled=config.default_mic_enabled,
        )
        self.events: queue.Queue[dict[str, object]] = queue.Queue()
        self.commands: queue.Queue[tuple[str, object | None]] = queue.Queue()
        self.webcam_controller = WebcamWindowController(config)
        self.session: RecordingSession | None = None
        self.active_segment: ActiveSegment | None = None
        self.stop_requested = False
        self._refresh_capabilities()
        self._publish_state()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        if self.config.default_webcam_enabled:
            self.send("toggle_webcam", True)

    def _refresh_capabilities(self) -> None:
        pulse_sources = get_pulse_sources()
        self.state.ffmpeg_available = shutil.which("ffmpeg") is not None
        self.state.ffplay_available = shutil.which("ffplay") is not None
        self.state.webcam_available = Path(self.config.webcam_device).exists()
        self.state.webcam_flipped = self.config.webcam_flip_horizontal
        self.state.mic_available = pick_default_mic_source(pulse_sources) is not None
        self.state.desktop_audio_available = pick_default_desktop_source(pulse_sources) is not None

        if not self.state.ffmpeg_available:
            self.state.status = "ffmpeg is required but not installed or not in PATH."
        elif not self.config.display:
            self.state.status = "DISPLAY is not set."
        elif self.state.status == "Checking environment...":
            self.state.status = "Ready."

    def _publish_state(self) -> None:
        if self.state.webcam_enabled:
            self.state.webcam_preview_running = self.webcam_controller.ensure_running()
        else:
            self.state.webcam_preview_running = False
        self.events.put({"type": "state", "state": asdict(self.state)})

    def send(self, name: str, payload: object | None = None) -> None:
        self.commands.put((name, payload))

    def _run_loop(self) -> None:
        while not self.stop_requested:
            try:
                name, payload = self.commands.get(timeout=0.25)
            except queue.Empty:
                self._poll_background_processes()
                continue

            try:
                if name == "toggle_webcam":
                    self._handle_toggle_webcam(bool(payload))
                elif name == "toggle_webcam_flip":
                    self._handle_toggle_webcam_flip(bool(payload))
                elif name == "toggle_mic":
                    self._handle_toggle_mic(bool(payload))
                elif name == "start":
                    self._handle_start()
                elif name == "pause":
                    self._handle_pause()
                elif name == "stop":
                    self._handle_stop()
                elif name == "shutdown":
                    self._handle_shutdown()
                else:
                    self.state.status = f"Unknown command: {name}"
            except Exception as err:  # pragma: no cover - defensive UI safety.
                self.state.busy = False
                self.state.status = str(err)
            finally:
                self._refresh_capabilities()
                self._publish_state()

    def _poll_background_processes(self) -> None:
        state_changed = False
        preview_running = False
        if self.state.webcam_enabled:
            preview_running = self.webcam_controller.ensure_running()
            if not preview_running and self.state.webcam_enabled:
                self.state.webcam_enabled = False
                self.state.status = "Webcam preview disabled."
                state_changed = True
        if self.state.webcam_preview_running != preview_running:
            self.state.webcam_preview_running = preview_running
            state_changed = True

        if self.active_segment and self.active_segment.process.poll() is not None:
            kept, message = self._collect_finished_segment()
            self.active_segment = None
            if self.session and self.session.segments:
                self.state.mode = "paused"
                self.state.status = message or "Recording stopped unexpectedly. Press Start to resume."
            else:
                self.state.mode = "idle"
                self.state.current_output = ""
                self.state.status = message or "Recording stopped unexpectedly."
                self._clear_session_files(keep_segments=kept)
                self.session = None
            state_changed = True

        if state_changed:
            self._publish_state()

    def _handle_toggle_webcam(self, enabled: bool) -> None:
        self.state.busy = True
        self._refresh_capabilities()
        if enabled:
            if not self.state.ffplay_available:
                self.state.webcam_enabled = False
                self.state.status = "ffplay is required for the webcam preview."
                self.state.busy = False
                return
            if not self.state.webcam_available:
                self.state.webcam_enabled = False
                self.state.status = f"Webcam device not found: {self.config.webcam_device}"
                self.state.busy = False
                return
            self.webcam_controller.start()
            self.state.webcam_enabled = True
            self.state.status = "Webcam preview enabled."
        else:
            self.webcam_controller.stop()
            self.state.webcam_enabled = False
            self.state.status = "Webcam preview disabled."
        self.state.busy = False

    def _handle_toggle_webcam_flip(self, enabled: bool) -> None:
        previous = self.config.webcam_flip_horizontal
        if previous == enabled:
            return

        self.state.busy = True
        self.config.webcam_flip_horizontal = enabled
        self.state.webcam_flipped = enabled

        if self.state.webcam_enabled:
            self.webcam_controller.stop()
            try:
                self.webcam_controller.start()
            except Exception:
                self.config.webcam_flip_horizontal = previous
                self.state.webcam_flipped = previous
                try:
                    self.webcam_controller.start()
                except Exception:
                    self.state.webcam_enabled = False
                raise

        self.state.status = "Webcam flipped." if enabled else "Webcam flip disabled."
        self.state.busy = False

    def _handle_toggle_mic(self, enabled: bool) -> None:
        self.state.busy = True
        self._refresh_capabilities()
        if enabled and not self.state.mic_available:
            self.state.mic_enabled = False
            self.state.status = "No microphone source is available right now."
            self.state.busy = False
            return

        if self.state.mic_enabled == enabled:
            self.state.busy = False
            return

        self.state.mic_enabled = enabled
        if self.state.mode == "recording":
            self.state.status = "Applying microphone change..."
            self._rotate_segment()
            if self.state.mode == "recording":
                state_text = "enabled" if enabled else "disabled"
                self.state.status = f"Microphone {state_text}."
        else:
            state_text = "enabled" if enabled else "disabled"
            self.state.status = f"Microphone {state_text}."
        self.state.busy = False

    def _handle_start(self) -> None:
        if not self.state.ffmpeg_available:
            self.state.status = "ffmpeg is required but not installed or not in PATH."
            return

        self.state.busy = True
        self._refresh_capabilities()
        if self.state.mode == "recording":
            self.state.busy = False
            return

        if self.session is None:
            final_output = next_available_output_path()
            final_output.parent.mkdir(parents=True, exist_ok=True)
            temp_dir = Path(tempfile.mkdtemp(prefix="smriti-", dir="/tmp"))
            self.session = RecordingSession(final_output=final_output, temp_dir=temp_dir)
            self.state.current_output = str(final_output)

        self._start_segment()
        self.state.mode = "recording"
        self.state.busy = False

    def _handle_pause(self) -> None:
        if self.state.mode != "recording":
            return

        self.state.busy = True
        self.state.status = "Pausing recording..."
        self._stop_current_segment()
        self.state.mode = "paused"
        self.state.status = "Paused."
        self.state.busy = False

    def _handle_stop(self) -> None:
        if self.session is None and self.active_segment is None:
            self.state.mode = "idle"
            self.state.status = "Ready."
            return

        self.state.busy = True
        self.state.status = "Finalizing recording..."
        saved_path: Path | None = None
        reveal_result: str | None = None
        try:
            if self.state.mode == "recording":
                self._stop_current_segment()
            saved_path = self._finalize_session()
            if saved_path:
                reveal_result = reveal_in_file_manager(saved_path)
        finally:
            self.state.mode = "idle"
            self.state.current_output = ""
            self.state.busy = False

        self.state.last_output = str(saved_path) if saved_path else self.state.last_output
        if saved_path:
            if reveal_result == "selected":
                self.state.status = "Saved recording and selected it in your file manager."
            elif reveal_result == "opened":
                self.state.status = "Saved recording and opened its folder."
            else:
                self.state.status = "Saved recording, but couldn't open its folder."
        else:
            self.state.status = "Nothing was saved."

    def _handle_shutdown(self) -> None:
        self.state.busy = True
        try:
            if self.state.mode == "recording":
                self._stop_current_segment()
            if self.session is not None:
                saved_path = self._finalize_session()
                if saved_path:
                    self.state.last_output = str(saved_path)
        finally:
            self.webcam_controller.stop()
            self.state.webcam_enabled = False
            self.state.mode = "idle"
            self.state.current_output = ""
            self.state.busy = False
            self.stop_requested = True

    def _start_segment(self) -> None:
        assert self.session is not None

        segment_path = self.session.temp_dir / f"segment-{len(self.session.segments) + 1:04d}.mp4"
        command, warnings = build_segment_command(
            config=self.config,
            output_path=segment_path,
            mic_enabled=self.state.mic_enabled,
        )
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        time.sleep(0.8)
        if process.poll() is not None:
            stderr_output = read_pipe(process.stderr)
            raise RuntimeError(summarize_error("Failed to start recording.", stderr_output))

        self.active_segment = ActiveSegment(path=segment_path, process=process)
        if warnings:
            self.state.status = " ".join(warnings)
        else:
            self.state.status = "Recording..."

    def _rotate_segment(self) -> None:
        self._stop_current_segment()
        if self.session is None:
            return
        self.state.mode = "paused"
        self._start_segment()
        self.state.mode = "recording"

    def _stop_current_segment(self) -> None:
        if not self.active_segment:
            return

        process = self.active_segment.process
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)

        kept, message = self._collect_finished_segment()
        self.active_segment = None
        if message:
            self.state.status = message
        if not kept and self.session and not self.session.segments:
            self.state.status = "The latest segment could not be finalized."

    def _collect_finished_segment(self) -> tuple[bool, str | None]:
        if not self.active_segment or self.session is None:
            return False, None

        segment_path = self.active_segment.path
        process = self.active_segment.process
        stderr_output = read_pipe(process.stderr)
        if process.stderr:
            process.stderr.close()

        playable = has_playable_video_stream(segment_path)
        if playable:
            self.session.segments.append(segment_path)
            if process.returncode not in (0, 130, 255, -2):
                return True, summarize_error(
                    "Recorder exited with a warning; kept the segment.",
                    stderr_output,
                )
            return True, None

        if segment_path.exists():
            return False, summarize_error("Discarded an incomplete segment.", stderr_output)
        return False, summarize_error("Recorder stopped without producing a playable segment.", stderr_output)

    def _finalize_session(self) -> Path | None:
        if self.session is None:
            return None

        success = False
        result: Path | None = None
        temp_dir = self.session.temp_dir
        try:
            if not self.session.segments:
                self._clear_session_files(keep_segments=False)
                return None

            self.session.final_output.parent.mkdir(parents=True, exist_ok=True)
            if len(self.session.segments) == 1:
                shutil.move(str(self.session.segments[0]), str(self.session.final_output))
                result = self.session.final_output
                success = True
                return result

            concat_list = self.session.temp_dir / "segments.txt"
            concat_lines = [
                f"file '{quote_concat_path(segment)}'" for segment in self.session.segments
            ]
            concat_list.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")

            merged_copy = self.session.temp_dir / "merged-copy.mp4"
            copy_proc = subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(concat_list),
                    "-c",
                    "copy",
                    "-movflags",
                    "+faststart",
                    str(merged_copy),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            if copy_proc.returncode == 0 and has_playable_video_stream(merged_copy):
                shutil.move(str(merged_copy), str(self.session.final_output))
                result = self.session.final_output
                success = True
                return result

            merged_reencode = self.session.temp_dir / "merged-reencode.mp4"
            reencode_proc = subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(concat_list),
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "23",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "160k",
                    "-ac",
                    "2",
                    "-ar",
                    "48000",
                    "-movflags",
                    "+faststart",
                    str(merged_reencode),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            if reencode_proc.returncode == 0 and has_playable_video_stream(merged_reencode):
                shutil.move(str(merged_reencode), str(self.session.final_output))
                result = self.session.final_output
                success = True
                return result

            copy_error = summarize_error("Merge failed.", copy_proc.stderr or "")
            reencode_error = summarize_error("Fallback merge failed.", reencode_proc.stderr or "")
            raise RuntimeError(f"{copy_error} {reencode_error}".strip())
        except Exception as err:
            self.session = None
            raise RuntimeError(f"{err} Segment files were kept in {temp_dir}.") from err
        finally:
            if success:
                self._clear_session_files(keep_segments=False)

        return result

    def _clear_session_files(self, keep_segments: bool) -> None:
        if self.session is None:
            return

        temp_dir = self.session.temp_dir
        if keep_segments:
            return
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        self.session = None
