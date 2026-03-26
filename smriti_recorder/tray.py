from __future__ import annotations

import queue
import sys
import time
import os
import tempfile

try:
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as AppIndicator3
    from gi.repository import GLib, Gtk
except (ImportError, ValueError):  # pragma: no cover - depends on local system packages.
    AppIndicator3 = None
    GLib = None
    Gtk = None

from .config import APP_NAME, AppConfig, ControllerState
from .controller import RecorderController
from .desktop import ensure_runtime_desktop_entry, find_app_icon_path, find_asset_path


def tray_backend_available() -> bool:
    return AppIndicator3 is not None and GLib is not None and Gtk is not None


if not tray_backend_available():
    class TrayApp:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("GTK and Ayatana AppIndicator are required to run the tray UI.")


else:
    class TrayApp:
        POLL_INTERVAL_MS = 150
        TIMER_INTERVAL_S = 1

        def __init__(self, config: AppConfig | None = None) -> None:
            self.state: ControllerState | None = None
            self.closing = False
            self.syncing_menu = False
            self.recording_started_monotonic: float | None = None
            self.last_mode = "idle"
            self.controller = RecorderController(config or AppConfig())
            self.indicator = AppIndicator3.Indicator.new(
                APP_NAME,
                APP_NAME,
                AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
            )
            self._set_indicator_icon()
            self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
            self.indicator.set_ordering_index(2)

            self.transparent_icon_path = os.path.join(tempfile.gettempdir(), f"{APP_NAME}_transparent.svg")
            try:
                with open(self.transparent_icon_path, "w") as f:
                    f.write("<svg xmlns='http://www.w3.org/2000/svg' width='1' height='1'></svg>")
            except OSError:
                pass

            self.timer_indicator = AppIndicator3.Indicator.new(
                APP_NAME + "_timer",
                APP_NAME + "_timer",
                AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
            )
            stop_path = find_asset_path("stop.png")
            self.stop_icon_path = self.transparent_icon_path
            if stop_path:
                self.stop_icon_path = str(stop_path)
                try:
                    from PIL import Image
                    with Image.open(stop_path) as img:
                        bbox = img.convert("RGBA").getchannel("A").getbbox()
                        if bbox:
                            temp_stop = os.path.join(tempfile.gettempdir(), f"{APP_NAME}_stop_maxed.png")
                            img.crop(bbox).save(temp_stop)
                            self.stop_icon_path = temp_stop
                except Exception:
                    pass
            self.timer_indicator.set_icon_full(self.stop_icon_path, "Stop")
            self.timer_indicator.set_status(AppIndicator3.IndicatorStatus.PASSIVE)
            self.timer_indicator.set_ordering_index(1)

            self.menu = Gtk.Menu()
            self.transport_item = Gtk.MenuItem(label="Start Recording")
            self.transport_item.connect("activate", self.on_primary_action)
            self.menu.append(self.transport_item)

            self.menu.append(Gtk.SeparatorMenuItem())

            self.mic_item = Gtk.CheckMenuItem(label="Mic")
            self.mic_item.connect("toggled", self.on_toggle_mic)
            self.menu.append(self.mic_item)

            self.menu.append(Gtk.SeparatorMenuItem())

            self.webcam_item = Gtk.CheckMenuItem(label="Camera")
            self.webcam_item.connect("toggled", self.on_toggle_webcam)
            self.menu.append(self.webcam_item)

            self.flip_camera_item = Gtk.CheckMenuItem(label="Flip Camera")
            self.flip_camera_item.connect("toggled", self.on_toggle_webcam_flip)
            self.menu.append(self.flip_camera_item)

            self.menu.append(Gtk.SeparatorMenuItem())

            self.quit_item = Gtk.MenuItem(label="Quit")
            self.quit_item.connect("activate", self.on_quit)
            self.menu.append(self.quit_item)

            self.menu.show_all()
            self.indicator.set_menu(self.menu)
            
            self.timer_indicator.set_menu(self.menu)
            self.timer_indicator.set_secondary_activate_target(self.transport_item)

            self._apply_state(self.controller.state.__dict__)
            GLib.timeout_add(self.POLL_INTERVAL_MS, self._poll_events)
            GLib.timeout_add_seconds(self.TIMER_INTERVAL_S, self._update_indicator_timer)

        def _set_indicator_icon(self) -> None:
            icon_path = find_app_icon_path()
            if icon_path is not None:
                self.indicator.set_icon_full(str(icon_path), APP_NAME)
                return
            self.indicator.set_icon(APP_NAME)

        def _poll_events(self) -> bool:
            while True:
                try:
                    event = self.controller.events.get_nowait()
                except queue.Empty:
                    break
                if event.get("type") == "state":
                    self._apply_state(event["state"])
            return True

        def _sync_check_item(self, item: Gtk.CheckMenuItem, active: bool) -> None:
            if item.get_active() == active:
                return
            item.set_active(active)

        def _sync_recording_timer(self, state: ControllerState) -> None:
            if state.mode == "recording":
                if self.last_mode != "recording":
                    self.recording_started_monotonic = time.monotonic()
            else:
                self.recording_started_monotonic = None
            self.last_mode = state.mode

        def _format_elapsed(self) -> str:
            if self.recording_started_monotonic is None:
                return ""
            total_seconds = int(max(0.0, time.monotonic() - self.recording_started_monotonic))
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            if hours:
                return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            return f"{minutes:02d}:{seconds:02d}"

        def _update_indicator_timer(self) -> bool:
            if self.state is None or self.state.mode != "recording":
                self.timer_indicator.set_label("", "")
                self.timer_indicator.set_status(AppIndicator3.IndicatorStatus.PASSIVE)
                return True

            self.timer_indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
            self.timer_indicator.set_label(self._format_elapsed(), "00:00:00")
            return True

        def _apply_state(self, raw_state: object) -> None:
            assert isinstance(raw_state, dict)
            self.state = ControllerState(**raw_state)

            state = self.state
            self._sync_recording_timer(state)
            controls_disabled = state.busy or self.closing
            can_record = state.ffmpeg_available and not controls_disabled
            is_stop_mode = state.mode in {"recording", "paused"}

            self.syncing_menu = True
            try:
                self._sync_check_item(self.webcam_item, state.webcam_enabled)
                self._sync_check_item(self.flip_camera_item, state.webcam_flipped)
                self._sync_check_item(self.mic_item, state.mic_enabled)
            finally:
                self.syncing_menu = False

            self.webcam_item.set_sensitive(not controls_disabled)
            self.flip_camera_item.set_sensitive(not controls_disabled)
            self.mic_item.set_sensitive(not controls_disabled)
            self.transport_item.set_label("Stop Recording" if is_stop_mode else "Start Recording")
            self.transport_item.set_sensitive((not controls_disabled and is_stop_mode) or can_record)
            self.quit_item.set_sensitive(not self.closing)
            self._update_indicator_timer()

        def on_toggle_webcam(self, item: Gtk.CheckMenuItem) -> None:
            if self.syncing_menu or not self.state or self.state.busy or self.closing:
                return
            self.controller.send("toggle_webcam", item.get_active())

        def on_toggle_webcam_flip(self, item: Gtk.CheckMenuItem) -> None:
            if self.syncing_menu or not self.state or self.state.busy or self.closing:
                return
            self.controller.send("toggle_webcam_flip", item.get_active())

        def on_toggle_mic(self, item: Gtk.CheckMenuItem) -> None:
            if self.syncing_menu or not self.state or self.state.busy or self.closing:
                return
            self.controller.send("toggle_mic", item.get_active())

        def on_primary_action(self, _item: Gtk.MenuItem) -> None:
            if not self.state or self.state.busy or self.closing:
                return
            if self.state.mode in {"recording", "paused"}:
                self.controller.send("stop")
                return
            self.controller.send("start")

        def on_quit(self, _item: Gtk.MenuItem) -> None:
            if self.closing:
                return
            self.closing = True
            if self.state is not None:
                self._apply_state(self.state.__dict__)
            self.controller.send("shutdown")
            GLib.timeout_add(self.POLL_INTERVAL_MS, self._wait_for_shutdown)

        def _wait_for_shutdown(self) -> bool:
            if self.controller.thread.is_alive():
                return True
            Gtk.main_quit()
            return False


def launch_tray() -> int:
    if not tray_backend_available():
        print("GTK and Ayatana AppIndicator are required to run the tray UI.", file=sys.stderr)
        return 1

    initialized, _argv = Gtk.init_check(None)
    if not initialized:
        print("A GTK display session is required to run the tray UI.", file=sys.stderr)
        return 1

    ensure_runtime_desktop_entry()
    app = TrayApp()
    Gtk.main()
    del app
    return 0
