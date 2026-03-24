from __future__ import annotations

import math
import queue
import socket
import sys

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - depends on local system packages.
    tk = None

from .config import AppConfig, ControllerState
from .controller import RecorderController
from .desktop import (
    detect_icon_content_box,
    ensure_runtime_desktop_entry,
    find_app_class_name,
    find_app_icon_path,
)

if tk is not None:
    from .ui import IconControl, UI_THEME


if tk is None:
    class RecorderApp:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("tkinter is required to run the smriti GUI.")


else:
    class RecorderApp:
        POLL_INTERVAL_MS = 150

        def __init__(self, root: tk.Tk) -> None:
            self.root = root
            self.icon_source_image: tk.PhotoImage | None = None
            self.icon_images: list[tk.PhotoImage] = []
            self.root.title("smriti")
            self.root.resizable(False, False)
            self.root.protocol("WM_DELETE_WINDOW", self.on_close)
            self._set_window_manager_hints()
            self._set_window_icon()

            self.closing = False
            self.state: ControllerState | None = None
            self.controller = RecorderController(AppConfig())

            self._build_ui()
            self._poll_events()

        def _set_window_manager_hints(self) -> None:
            try:
                self.root.wm_client(socket.gethostname())
            except tk.TclError:
                pass
            try:
                if self.root.tk.call("tk", "windowingsystem") == "x11":
                    self.root.wm_attributes("-type", "normal")
            except tk.TclError:
                pass

        def _set_window_icon(self) -> None:
            icon_path = find_app_icon_path()
            if icon_path is None:
                return
            try:
                self.icon_source_image = tk.PhotoImage(file=str(icon_path), master=self.root)
                source = self.icon_source_image
                width = source.width()
                height = source.height()
                content_box = detect_icon_content_box(icon_path, width, height)
                content_width = content_box[2] - content_box[0]
                content_height = content_box[3] - content_box[1]

                # X11 stores Tk icons in _NET_WM_ICON. Sending the full source image
                # can exceed server request limits when the asset is very large.
                # Tk recommends providing a small set of icon sizes, with the larger
                # one first, so window managers can pick an appropriate variant.
                variants: list[tk.PhotoImage] = []
                for target_size in (128, 32):
                    x_scale = max(1, math.ceil(content_width / target_size))
                    y_scale = max(1, math.ceil(content_height / target_size))
                    variant = tk.PhotoImage(master=self.root)
                    variant.tk.call(
                        str(variant),
                        "copy",
                        str(source),
                        "-from",
                        content_box[0],
                        content_box[1],
                        content_box[2],
                        content_box[3],
                        "-shrink",
                        "-subsample",
                        x_scale,
                        y_scale,
                    )
                    if any(
                        existing.width() == variant.width() and existing.height() == variant.height()
                        for existing in variants
                    ):
                        continue
                    variants.append(variant)

                if not variants:
                    variants = [source]

                self.icon_images = variants
                self.root.iconphoto(True, *self.icon_images)
            except tk.TclError:
                self.icon_source_image = None
                self.icon_images = []

        def _build_ui(self) -> None:
            theme = UI_THEME
            self.root.configure(bg=theme["control_panel_bg"])

            self.controls_card = tk.Frame(
                self.root,
                bg=theme["control_panel_bg"],
                padx=12,
                pady=12,
                highlightthickness=1,
                highlightbackground=theme["control_panel_outline"],
            )
            self.controls_card.pack()

            self.controls_row = tk.Frame(self.controls_card, bg=theme["control_panel_bg"])
            self.controls_row.pack()

            self.webcam_button = IconControl(
                self.controls_row,
                label="",
                icon_kind="webcam",
                command=self.on_toggle_webcam,
                accent=theme["accent_toggle"],
                background=theme["control_panel_bg"],
                variant="toggle",
                width=78,
                height=72,
            )
            self.webcam_button.pack(side="left", padx=(0, 8))

            self.mic_button = IconControl(
                self.controls_row,
                label="",
                icon_kind="mic",
                command=self.on_toggle_mic,
                accent=theme["accent_toggle"],
                background=theme["control_panel_bg"],
                variant="toggle",
                width=78,
                height=72,
            )
            self.mic_button.pack(side="left", padx=(0, 12))

            self.controls_divider = tk.Frame(
                self.controls_row,
                width=1,
                height=44,
                bg=theme["control_panel_outline"],
            )
            self.controls_divider.pack(side="left", padx=(0, 12), pady=14)

            self.start_button = IconControl(
                self.controls_row,
                label="",
                icon_kind="record",
                command=self.on_primary_action,
                accent=theme["accent_record"],
                background=theme["control_panel_bg"],
                variant="transport",
                width=84,
                height=72,
            )
            self.start_button.pack(side="left")

            self.output_label = tk.Label(
                self.root,
                text="",
                anchor="w",
                justify="left",
                font=("TkFixedFont", 9),
                bg=theme["control_panel_bg"],
                fg=theme["control_text"],
                wraplength=280,
            )
            self.output_visible = False

        def on_toggle_webcam(self) -> None:
            if not self.state or self.state.busy:
                return
            self.controller.send("toggle_webcam", not self.state.webcam_enabled)

        def on_toggle_mic(self) -> None:
            if not self.state or self.state.busy:
                return
            self.controller.send("toggle_mic", not self.state.mic_enabled)

        def on_start(self) -> None:
            if not self.state or self.state.busy:
                return
            self.controller.send("start")

        def on_primary_action(self) -> None:
            if not self.state or self.state.busy:
                return
            if self.state.mode in {"recording", "paused"}:
                self.controller.send("stop")
                return
            self.controller.send("start")

        def on_pause(self) -> None:
            if not self.state or self.state.busy:
                return
            self.controller.send("pause")

        def on_stop(self) -> None:
            if not self.state or self.state.busy:
                return
            self.controller.send("stop")

        def on_close(self) -> None:
            if self.closing:
                return
            self.closing = True
            self.start_button.set_visual_state(enabled=False)
            self.webcam_button.set_visual_state(enabled=False)
            self.mic_button.set_visual_state(enabled=False)
            self.controller.send("shutdown")
            self._wait_for_shutdown()

        def _wait_for_shutdown(self) -> None:
            if self.controller.thread.is_alive():
                self.root.after(self.POLL_INTERVAL_MS, self._wait_for_shutdown)
                return
            self.root.destroy()

        def _poll_events(self) -> None:
            while True:
                try:
                    event = self.controller.events.get_nowait()
                except queue.Empty:
                    break
                if event.get("type") == "state":
                    self._apply_state(event["state"])
            self.root.after(self.POLL_INTERVAL_MS, self._poll_events)

        def _apply_state(self, raw_state: object) -> None:
            assert isinstance(raw_state, dict)
            self.state = ControllerState(**raw_state)

            state = self.state

            controls_disabled = state.busy or self.closing
            can_record = state.ffmpeg_available and not controls_disabled

            self.start_button.set_visual_state(
                label="",
                icon_kind="stop" if state.mode in {"recording", "paused"} else "record",
                enabled=(not controls_disabled and state.mode in {"recording", "paused"}) or can_record,
                active=False,
            )
            self.webcam_button.set_visual_state(
                label="",
                icon_kind="webcam",
                active=state.webcam_enabled,
                enabled=not controls_disabled,
            )
            self.mic_button.set_visual_state(
                label="",
                icon_kind="mic",
                active=state.mic_enabled,
                enabled=not controls_disabled,
            )

            output_path = state.last_output if state.mode == "idle" and state.last_output else ""
            if output_path:
                self.output_label.configure(text=output_path)
                if not self.output_visible:
                    self.output_label.pack(fill="x", pady=(10, 0))
                    self.output_visible = True
            elif self.output_visible:
                self.output_label.pack_forget()
                self.output_visible = False


def launch_gui() -> int:
    if tk is None:
        print("tkinter is required to run the smriti GUI.", file=sys.stderr)
        return 1

    ensure_runtime_desktop_entry()
    app_class_name = find_app_class_name()
    root = tk.Tk(baseName=app_class_name, className=app_class_name)
    app = RecorderApp(root)
    root.mainloop()
    return 0


def main() -> int:
    return launch_gui()
