# scrnrcdr (X11 minimal recorder)

Minimal Linux screen recorder for X11 using `ffmpeg` with:

- whole desktop or region capture
- optional webcam:
  - draggable window mode (default)
  - ffmpeg overlay mode (fallback)
- optional microphone and optional desktop audio

## Requirements

- Linux X11 session
- `ffmpeg` installed and available in `PATH`
- `pactl` available for auto audio source detection (typically PulseAudio or PipeWire Pulse)

## Quick start

```bash
python3 recorder.py
```

This records the whole desktop to a timestamped MP4 in the current directory.

Stop recording with `Ctrl+C`.

## Common usage

Record desktop + mic + desktop audio:

```bash
python3 recorder.py --mic --desktop-audio
```

Add webcam (window mode by default, width 320):

```bash
python3 recorder.py --webcam --mic --desktop-audio
```

Webcam window mode controls while recording:

- drag webcam window with mouse to place anywhere
- put another window on top to hide webcam from recording
- press `Ctrl+C` in recorder terminal to stop recording

Move webcam overlay (overlay mode only):

```bash
python3 recorder.py --webcam --webcam-mode overlay --webcam-x 20 --webcam-y 20
```

Set webcam width (works in both modes):

```bash
python3 recorder.py --webcam --webcam-width 420
```

Set webcam window initial position (window mode):

```bash
python3 recorder.py --webcam --webcam-window-x 80 --webcam-window-y 60
```

Record a region only (`WIDTHxHEIGHT+X,Y`):

```bash
python3 recorder.py --region 1280x720+100,80
```

Set output path:

```bash
python3 recorder.py --output ~/Videos/demo.mp4
```

Show generated ffmpeg command before start:

```bash
python3 recorder.py --show-command --webcam --mic --desktop-audio
```

## Device/source helpers

List audio sources:

```bash
python3 recorder.py --list-audio-sources
```

List webcam/video devices:

```bash
python3 recorder.py --list-video-devices
```

Use specific sources/devices:

```bash
python3 recorder.py \
  --mic --desktop-audio --webcam \
  --mic-source alsa_input.usb-YourMic \
  --desktop-source alsa_output.pci-0000_00_1f.3.analog-stereo.monitor \
  --webcam-device /dev/video2
```

## Notes

- This tool is intentionally X11-focused.
- Browser-tab capture is not implemented.
- Window-only capture is not implemented yet (region capture is available now).
- Webcam mode defaults to `window` for mouse drag and overlap behavior.
- To keep MP4 playable, stop with `Ctrl+C` and wait for finalization message.

## Repository housekeeping

- A `.gitignore` is included to ignore Python cache files and local recording outputs.
- If `__pycache__/` already exists locally, it is safe to delete.
