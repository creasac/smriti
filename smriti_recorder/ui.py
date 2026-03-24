from __future__ import annotations

import math
from typing import Callable

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - depends on local system packages.
    tk = None

from .desktop import ASSET_FILENAMES, detect_icon_content_box, find_asset_path

UI_THEME = {
    "window_bg": "#0b0f14",
    "panel_bg": "#131922",
    "panel_alt": "#1a222d",
    "control_panel_bg": "#f5f5f5",
    "control_panel_outline": "#d2d9e2",
    "control_text": "#202833",
    "control_text_muted": "#8d98a6",
    "outline": "#283343",
    "outline_soft": "#202a36",
    "text_primary": "#f3efe8",
    "text_secondary": "#a5b1c2",
    "text_muted": "#6f7b8b",
    "accent_record": "#ff7a59",
    "accent_pause": "#d3b06e",
    "accent_stop": "#f19082",
    "accent_toggle": "#74c4a0",
    "accent_idle": "#7d8ca3",
}


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def blend(color_a: str, color_b: str, factor: float) -> str:
    factor = clamp(factor, 0.0, 1.0)
    a = color_a.lstrip("#")
    b = color_b.lstrip("#")
    channels = [
        round(int(a[index : index + 2], 16) + (int(b[index : index + 2], 16) - int(a[index : index + 2], 16)) * factor)
        for index in (0, 2, 4)
    ]
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def draw_rounded_rectangle(
    canvas: tk.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    radius: float,
    *,
    fill: str,
    outline: str,
    width: int = 1,
) -> int:
    radius = clamp(radius, 0, min((x2 - x1) / 2, (y2 - y1) / 2))
    points = [
        x1 + radius,
        y1,
        x1 + radius,
        y1,
        x2 - radius,
        y1,
        x2 - radius,
        y1,
        x2,
        y1,
        x2,
        y1 + radius,
        x2,
        y1 + radius,
        x2,
        y2 - radius,
        x2,
        y2 - radius,
        x2,
        y2,
        x2 - radius,
        y2,
        x2 - radius,
        y2,
        x1 + radius,
        y2,
        x1 + radius,
        y2,
        x1,
        y2,
        x1,
        y2 - radius,
        x1,
        y2 - radius,
        x1,
        y1 + radius,
        x1,
        y1 + radius,
        x1,
        y1,
    ]
    return canvas.create_polygon(
        points,
        smooth=True,
        splinesteps=32,
        fill=fill,
        outline=outline,
        width=width,
    )


if tk is None:
    class StatusBadge:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("tkinter is required to use the smriti UI.")


    class IconControl:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("tkinter is required to use the smriti UI.")


else:
    class StatusBadge(tk.Frame):
        def __init__(self, master: tk.Misc, *, width: int, height: int, background: str) -> None:
            super().__init__(master, bg=background)
            self._width = width
            self._height = height
            self._text = ""
            self._fill = UI_THEME["panel_alt"]
            self._outline = UI_THEME["outline"]
            self._text_color = UI_THEME["text_secondary"]
            self._dot = UI_THEME["accent_idle"]
            self.canvas = tk.Canvas(
                self,
                width=width,
                height=height,
                bg=background,
                bd=0,
                highlightthickness=0,
            )
            self.canvas.pack()
            self.render()

        def set_badge(self, *, text: str, fill: str, outline: str, text_color: str, dot: str) -> None:
            self._text = text
            self._fill = fill
            self._outline = outline
            self._text_color = text_color
            self._dot = dot
            self.render()

        def render(self) -> None:
            self.canvas.delete("all")
            draw_rounded_rectangle(
                self.canvas,
                1,
                1,
                self._width - 1,
                self._height - 1,
                14,
                fill=self._fill,
                outline=self._outline,
            )
            self.canvas.create_oval(14, 11, 20, 17, fill=self._dot, outline="")
            self.canvas.create_text(
                self._width / 2 + 8,
                self._height / 2,
                text=self._text,
                font=("TkDefaultFont", 9, "bold"),
                fill=self._text_color,
            )


    class IconControl(tk.Frame):
        def __init__(
            self,
            master: tk.Misc,
            *,
            label: str,
            icon_kind: str,
            command: Callable[[], None] | None,
            secondary_command: Callable[[], None] | None = None,
            accent: str,
            background: str,
            variant: str = "toggle",
            width: int,
            height: int,
        ) -> None:
            super().__init__(master, bg=background)
            self.command = command
            self.secondary_command = secondary_command
            self.accent = accent
            self.background = background
            self.variant = variant
            self.width = width
            self.height = height
            self.label = label
            self.icon_kind = icon_kind
            self.icon_images: dict[tuple[str, int], tk.PhotoImage | None] = {}
            self.enabled = True
            self.active = False
            self.hovered = False
            self.pressed = False
            self.canvas = tk.Canvas(
                self,
                width=width,
                height=height,
                bg=background,
                bd=0,
                highlightthickness=0,
            )
            self.canvas.pack()
            self._bind_events()
            self.render()

        def _bind_events(self) -> None:
            for sequence, handler in (
                ("<Enter>", self._on_enter),
                ("<Leave>", self._on_leave),
                ("<ButtonPress-1>", self._on_press),
                ("<ButtonRelease-1>", self._on_release),
                ("<ButtonRelease-3>", self._on_secondary_release),
            ):
                self.canvas.bind(sequence, handler)

        def _on_enter(self, _event: tk.Event[tk.Misc]) -> None:
            self.hovered = True
            self.render()

        def _on_leave(self, _event: tk.Event[tk.Misc]) -> None:
            self.hovered = False
            self.pressed = False
            self.render()

        def _on_press(self, _event: tk.Event[tk.Misc]) -> None:
            if not self.enabled or self.command is None:
                return
            self.pressed = True
            self.render()

        def _on_release(self, event: tk.Event[tk.Misc]) -> None:
            should_fire = (
                self.enabled
                and self.command is not None
                and self.pressed
                and 0 <= event.x <= self.width
                and 0 <= event.y <= self.height
            )
            self.pressed = False
            self.render()
            if should_fire:
                self.command()

        def _on_secondary_release(self, event: tk.Event[tk.Misc]) -> None:
            should_fire = (
                self.enabled
                and self.secondary_command is not None
                and 0 <= event.x <= self.width
                and 0 <= event.y <= self.height
            )
            self.pressed = False
            self.render()
            if should_fire:
                self.secondary_command()

        def set_visual_state(
            self,
            *,
            label: str | None = None,
            icon_kind: str | None = None,
            enabled: bool | None = None,
            active: bool | None = None,
            accent: str | None = None,
            variant: str | None = None,
        ) -> None:
            if label is not None:
                self.label = label
            if icon_kind is not None:
                self.icon_kind = icon_kind
            if enabled is not None:
                self.enabled = enabled
            if active is not None:
                self.active = active
            if accent is not None:
                self.accent = accent
            if variant is not None:
                self.variant = variant
            self.render()

        def _palette(self) -> tuple[str, str, str, str]:
            if self.variant == "transport":
                fill = self.accent
                outline = blend(self.accent, "#000000", 0.18)
                icon_color = UI_THEME["control_text"]
                label_color = UI_THEME["control_text"]

                if self.hovered and self.enabled:
                    fill = blend(fill, "#ffffff", 0.06)
                if self.pressed and self.enabled:
                    fill = blend(fill, "#000000", 0.10)
                if not self.enabled:
                    fill = blend(fill, self.background, 0.40)
                    outline = blend(outline, self.background, 0.34)
                    icon_color = UI_THEME["control_text_muted"]
                    label_color = UI_THEME["control_text_muted"]

                return fill, outline, icon_color, label_color

            fill = self.background
            outline = UI_THEME["control_panel_outline"]
            icon_color = UI_THEME["control_text"]
            label_color = UI_THEME["control_text"]

            if self.active:
                outline = blend(outline, self.accent, 0.48)
                icon_color = self.accent
                label_color = self.accent
            elif self.hovered and self.enabled:
                outline = blend(outline, UI_THEME["control_text"], 0.18)

            if not self.enabled:
                outline = blend(outline, self.background, 0.36)
                icon_color = UI_THEME["control_text_muted"]
                label_color = UI_THEME["control_text_muted"]
            elif self.pressed:
                outline = blend(outline, "#000000", 0.12)

            return fill, outline, icon_color, label_color

        def _draw_record_icon(self, cx: float, cy: float, size: float, color: str) -> None:
            radius = size * 0.28
            if self.active:
                ring = size * 0.52
                self.canvas.create_oval(
                    cx - ring,
                    cy - ring,
                    cx + ring,
                    cy + ring,
                    outline=blend(self.accent, UI_THEME["panel_bg"], 0.20),
                    width=2,
                )
            self.canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill=color, outline="")

        def _draw_play_icon(self, cx: float, cy: float, size: float, color: str) -> None:
            half = size * 0.42
            self.canvas.create_polygon(
                cx - half * 0.5,
                cy - half,
                cx + half,
                cy,
                cx - half * 0.5,
                cy + half,
                fill=color,
                outline="",
            )

        def _draw_pause_icon(self, cx: float, cy: float, size: float, color: str) -> None:
            bar_width = size * 0.18
            gap = size * 0.14
            bar_height = size * 0.50
            self.canvas.create_rectangle(
                cx - gap - bar_width,
                cy - bar_height,
                cx - gap,
                cy + bar_height,
                fill=color,
                outline="",
            )
            self.canvas.create_rectangle(
                cx + gap,
                cy - bar_height,
                cx + gap + bar_width,
                cy + bar_height,
                fill=color,
                outline="",
            )

        def _draw_stop_icon(self, cx: float, cy: float, size: float, color: str) -> None:
            half = size * 0.35
            self.canvas.create_rectangle(cx - half, cy - half, cx + half, cy + half, fill=color, outline="")

        def _draw_webcam_icon(self, cx: float, cy: float, size: float, color: str) -> None:
            body_width = size * 0.98
            body_height = size * 0.54
            x1 = cx - body_width / 2
            y1 = cy - body_height / 2 + 2
            x2 = cx + body_width / 2
            y2 = cy + body_height / 2 + 2
            draw_rounded_rectangle(
                self.canvas,
                x1,
                y1,
                x2,
                y2,
                size * 0.14,
                fill="",
                outline=color,
                width=2,
            )
            tab_height = size * 0.16
            self.canvas.create_rectangle(
                x1 + size * 0.18,
                y1 - tab_height,
                x1 + size * 0.52,
                y1 + size * 0.02,
                fill=color,
                outline=color,
            )
            lens_radius = size * 0.22
            self.canvas.create_oval(
                cx - lens_radius,
                cy - lens_radius + 2,
                cx + lens_radius,
                cy + lens_radius + 2,
                outline=color,
                width=2,
            )
            self.canvas.create_oval(cx - 2, cy, cx + 2, cy + 4, fill=color, outline="")

        def _draw_mic_icon(self, cx: float, cy: float, size: float, color: str) -> None:
            head_width = size * 0.24
            head_height = size * 0.38
            draw_rounded_rectangle(
                self.canvas,
                cx - head_width,
                cy - head_height - 4,
                cx + head_width,
                cy + head_height * 0.18 - 4,
                head_width,
                fill=color,
                outline=color,
            )
            self.canvas.create_line(
                cx,
                cy + head_height * 0.18 - 4,
                cx,
                cy + size * 0.42,
                fill=color,
                width=2,
                capstyle=tk.ROUND,
            )
            self.canvas.create_arc(
                cx - size * 0.42,
                cy - size * 0.14,
                cx + size * 0.42,
                cy + size * 0.56,
                start=200,
                extent=140,
                style=tk.ARC,
                outline=color,
                width=2,
            )
            self.canvas.create_line(
                cx - size * 0.28,
                cy + size * 0.48,
                cx + size * 0.28,
                cy + size * 0.48,
                fill=color,
                width=2,
                capstyle=tk.ROUND,
            )

        def _asset_icon_name(self) -> str | None:
            if self.icon_kind == "record":
                return ASSET_FILENAMES["record"]
            if self.icon_kind == "pause":
                return ASSET_FILENAMES["pause"]
            if self.icon_kind == "resume":
                return ASSET_FILENAMES["resume"]
            if self.icon_kind == "stop":
                return ASSET_FILENAMES["stop"]
            if self.icon_kind == "webcam":
                return ASSET_FILENAMES["webcam_on"] if self.active else ASSET_FILENAMES["webcam_off"]
            if self.icon_kind == "mic":
                return ASSET_FILENAMES["mic_on"] if self.active else ASSET_FILENAMES["mic_off"]
            return None

        def _load_asset_icon(self, filename: str, size: int) -> tk.PhotoImage | None:
            cache_key = (filename, size)
            if cache_key in self.icon_images:
                return self.icon_images[cache_key]

            icon_path = find_asset_path(filename)
            if icon_path is None:
                self.icon_images[cache_key] = None
                return None

            try:
                source = tk.PhotoImage(file=str(icon_path), master=self)
                width = source.width()
                height = source.height()
                content_box = detect_icon_content_box(icon_path, width, height)
                cropped = source
                if content_box != (0, 0, width, height):
                    cropped = tk.PhotoImage(master=self)
                    cropped.tk.call(
                        str(cropped),
                        "copy",
                        str(source),
                        "-from",
                        content_box[0],
                        content_box[1],
                        content_box[2],
                        content_box[3],
                        "-shrink",
                    )

                source_size = max(1, cropped.width(), cropped.height())
                if source_size == size:
                    image = cropped
                else:
                    divisor = math.gcd(source_size, size)
                    zoom = max(1, size // divisor)
                    subsample = max(1, source_size // divisor)
                    image = cropped.zoom(zoom, zoom)
                    if subsample > 1:
                        image = image.subsample(subsample, subsample)

                self.icon_images[cache_key] = image
                return image
            except tk.TclError:
                self.icon_images[cache_key] = None
                return None

        def _draw_icon(self, cx: float, cy: float, size: float, color: str) -> None:
            asset_icon_name = self._asset_icon_name()
            if asset_icon_name is not None:
                asset_icon = self._load_asset_icon(asset_icon_name, round(size))
                if asset_icon is not None:
                    self.canvas.create_image(cx, cy, image=asset_icon)
                    return

            if self.icon_kind == "record":
                self._draw_record_icon(cx, cy, size, color)
            elif self.icon_kind == "play":
                self._draw_play_icon(cx, cy, size, color)
            elif self.icon_kind == "pause":
                self._draw_pause_icon(cx, cy, size, color)
            elif self.icon_kind in {"play", "resume"}:
                self._draw_play_icon(cx, cy, size, color)
            elif self.icon_kind == "stop":
                self._draw_stop_icon(cx, cy, size, color)
            elif self.icon_kind == "webcam":
                self._draw_webcam_icon(cx, cy, size, color)
            elif self.icon_kind == "mic":
                self._draw_mic_icon(cx, cy, size, color)

        def render(self) -> None:
            fill, outline, icon_color, label_color = self._palette()
            self.canvas.delete("all")
            radius = 18
            draw_rounded_rectangle(
                self.canvas,
                1,
                1,
                self.width - 1,
                self.height - 1,
                radius,
                fill=fill,
                outline=outline,
            )

            icon_only = not self.label
            icon_y = self.height / 2 if icon_only else (26 if self.variant == "transport" else 25)
            if icon_only:
                icon_size = 29
            else:
                icon_size = 30 if self.variant == "transport" else 28
            self._draw_icon(self.width / 2, icon_y, icon_size, icon_color)
            if self.label:
                self.canvas.create_text(
                    self.width / 2,
                    self.height - 18,
                    text=self.label,
                    font=("TkDefaultFont", 9, "bold"),
                    fill=label_color,
                )

            cursor = "hand2" if self.enabled and self.command is not None else "arrow"
            self.canvas.configure(cursor=cursor)
