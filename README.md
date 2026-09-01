# C200 Control

A small Linux control panel for the Anker PowerConf C200. It uses the camera's standard V4L2 controls and shows a low-latency preview inside the app.

## What it controls

- Field of view through the camera's zoom control
- Pan, tilt, focus, exposure, white balance, and image tuning
- An automatic live preview with valid resolution and frame-rate combinations
- Last-used camera controls, restored the next time the app opens

Camera adjustments apply while the preview is running. Scrolling over a slider scrolls the page instead of changing the setting.

Resolution and frame rate belong to each video stream. Browsers and calling apps negotiate their own stream mode when they open the camera, so the app does not pretend it can force those settings globally.

Pause the preview before opening the camera in another app. Hardware image controls remain on the camera after the control panel closes.

Firmware updates and Anker-only controls are outside the V4L2 interface and are not supported.

## Requirements

- Python 3 with PyGObject
- GTK 4 and libadwaita
- `v4l2-ctl`
- GStreamer with its V4L2, JPEG, and appsink plugins

These are already present on a standard Omarchy installation.

## Run

```bash
./c200-control
```

Check camera access without opening the interface:

```bash
./c200-control --check
```

## Add to the Omarchy launcher

```bash
./install.sh
```

The installer adds `C200 Control` to the standard application launcher. Remove `~/.local/share/applications/c200-control.desktop` to uninstall the launcher entry.

Settings are stored in `~/.config/c200-control/settings.json` and are not part of this repository.

## Test

```bash
python3 -m unittest discover -s tests -v
```
