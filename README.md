# smriti

Minimal X11 desktop recorder with top-bar controls.

It opens a top-bar menu with:

- `Start` and `Stop`
- `Mic` toggle
- `Camera` toggle
- `Flip Camera` toggle
- auto-saved MP4 recordings in `~/Videos/smriti/`

The webcam preview is a separate draggable window. When it is visible on the desktop, it is captured in the recording.

`Mic`, `Camera`, and `Flip Camera` start enabled by default and can be deselected later.
While recording, the tray indicator shows a running timer label next to the icon.

## Requirements

- Linux X11 session
- `ffmpeg`
- `ffplay`
- `pactl` for desktop audio and mic auto-detection
- GTK AppIndicator support (`python3-gi` + Ayatana AppIndicator) for the top-bar menu
- Python `tkinter` for the fallback window UI

## Run

From the repository root:

```bash
./smriti
```

You can also run:

```bash
python3 recorder.py
```

To force the original window UI instead of the top-bar menu:

```bash
SMRITI_UI=window ./smriti
```

## Install

To install `smriti` as a real command and desktop app entry:

```bash
./install.sh
```

This installs:

- `~/.local/bin/smriti`
- `~/.local/bin/smriti-uninstall`
- `~/.local/share/smriti/`
- `~/.local/share/applications/smriti.desktop`
- `~/.local/share/icons/hicolor/*/apps/smriti.png`

The desktop entry uses the themed `smriti` icon installed into `hicolor`.

If `~/.local/bin` is not already on your `PATH`, the installer appends it to `~/.bashrc`.

## Uninstall

To remove the local user install:

```bash
./uninstall.sh
```

If you installed it first, you can also run:

```bash
smriti-uninstall
```

This removes the local command, desktop entry, themed icons, and the installed app files under `~/.local/share/smriti/`.
If `install.sh` added `~/.local/bin` to your `PATH`, the uninstaller removes that exact block from `~/.bashrc`.

## Recording behavior

- Desktop audio is captured automatically when available.
- The mic can be turned on or off at any time.
- The webcam preview can be turned on or off at any time.
- `Pause` and `Resume` keep the same recording session.
- `Stop` saves the current recording.
- After `Stop`, pressing `Start` creates a new recording right away.

## Notes

- This is intentionally X11-focused.
- The top-bar controller avoids a separate floating window, but the tray icon and any open menu are still part of the desktop and can appear in recordings.
- If the tray backend is unavailable, smriti falls back to the original small Tk window.
- If desktop audio is not available, smriti records silent audio instead of failing.
- If final merge fails after pause/resume or mic changes, the temporary segment files are kept and the app shows where they were left.
