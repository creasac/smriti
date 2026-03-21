# smriti

Minimal X11 desktop recorder with a small control window.

It opens a GUI with:

- `Webcam` toggle
- `Mic` toggle
- `Start`, `Pause`, and `Stop`
- auto-saved MP4 recordings in `~/Videos/smriti/`

The webcam preview is a separate draggable window. When it is visible on the desktop, it is captured in the recording. The control window can be collapsed with the arrow button, and starting a recording auto-collapses it.

## Requirements

- Linux X11 session
- `ffmpeg`
- `ffplay`
- `pactl` for desktop audio and mic auto-detection
- Python `tkinter`

## Run

From the repository root:

```bash
./smriti
```

You can also run:

```bash
python3 recorder.py
```

## Install

To install `smriti` as a real command and desktop app entry:

```bash
./install.sh
```

This installs:

- `~/.local/bin/smriti`
- `~/.local/share/smriti/`
- `~/.local/share/applications/smriti.desktop`

If `~/.local/bin` is not already on your `PATH`, the installer appends it to `~/.bashrc`.

## Recording behavior

- Desktop audio is captured automatically when available.
- The mic can be turned on or off at any time.
- The webcam preview can be turned on or off at any time.
- `Pause` and `Resume` keep the same recording session.
- `Stop` saves the current recording.
- After `Stop`, pressing `Start` creates a new recording right away.

## Notes

- This is intentionally X11-focused.
- The control window is part of the desktop, so if it is visible it can be recorded.
- If desktop audio is not available, smriti records silent audio instead of failing.
- If final merge fails after pause/resume or mic changes, the temporary segment files are kept and the app shows where they were left.
