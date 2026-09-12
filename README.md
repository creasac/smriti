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

<img width="160" height="160" alt="smriti_logo" src="https://github.com/user-attachments/assets/597a83c6-d2af-4fb2-8837-2dd156c8b148" />

## Requirements

- Linux X11 session
- `ffmpeg`
- `ffplay`
- `pactl` for desktop audio and mic auto-detection
- GTK AppIndicator support (`python3-gi` + Ayatana AppIndicator) for the top-bar menu
- Python `tkinter` for the fallback window UI

## Install

Run this as your normal user:

```bash
curl -fsSL https://raw.githubusercontent.com/creasac/smriti/master/bootstrap.sh | bash
```

No Git installation or clone is needed. The installer downloads a source archive
temporarily, copies the app into `~/.local/share/smriti`, and removes the download
on exit, including on failure. The installed app has no dependency on a checkout.

The installer checks dependencies before copying any app files. On Ubuntu/Debian:

```bash
sudo apt install python3 python3-tk ffmpeg pulseaudio-utils python3-gi gir1.2-ayatanaappindicator3-0.1
```

It reports missing dependencies instead of installing system packages for you.
GTK/AppIndicator support is optional; without it, Smriti uses the Tk window UI.
Python Pillow is optional for generating icons at multiple sizes.

This installs:

- `~/.local/bin/smriti`
- `~/.local/bin/smriti-uninstall`
- `~/.local/share/smriti/`
- `~/.local/share/applications/smriti.desktop`
- `~/.local/share/icons/hicolor/*/apps/smriti.png`

The desktop entry uses the themed `smriti` icon installed into `hicolor`.
The installer adds `~/.local/bin` to `~/.bashrc` if that PATH line is absent.
Open a new terminal or run `source ~/.bashrc` afterward. For other shells, add
`~/.local/bin` to your shell's PATH or use `~/.local/bin/smriti` directly.

## Run

Launch **smriti** from your app menu or run:

```bash
smriti
```

To use the window UI:

```bash
SMRITI_UI=window smriti
```

Developers can still run `./smriti` or `python3 recorder.py` from a source checkout.
`./install.sh` installs that checkout independently; you can delete it afterward.

## Uninstall

Stop any active recording and close Smriti, then run:

```bash
smriti-uninstall
```

You can also use `~/.local/bin/smriti-uninstall`, or `./uninstall.sh` from an
optional checkout. This removes both commands, desktop entries, themed icons,
and the installed app files. If the installer added a PATH block to `~/.bashrc`,
uninstall removes that exact block, including after a repeated installation.

**Your recordings in `~/Videos/smriti/` are always preserved.** System packages
and recovery segments from failed recordings are left in place.

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
