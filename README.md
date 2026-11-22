# C200 Control

A small Linux control panel for the Anker PowerConf C200. It uses the camera's standard V4L2 controls and shows a low-latency preview inside the app.

## What it controls

- Field of view through the camera's zoom control
- Pan, tilt, focus, white balance, and image tuning
- An automatic live preview with valid resolution and frame-rate combinations
- A persistent mirror toggle for the app's preview
- Last-used camera controls, applied to every app that uses the camera

Scrolling over a slider scrolls the page instead of changing the setting.

Resolution and frame rate belong to each video stream. Browsers and calling apps negotiate their own stream mode when they open the camera, so the app does not pretend it can force those settings globally.

The C200 preview supports H.264 at 60 fps up to 1920 x 1080, plus 2560 x 1440 at 30 fps. MJPEG preview modes run at 30 fps.

Pause the preview before opening the camera in another app.

## Settings in other apps

The C200 resets its picture, zoom included, whenever an app starts video, while still reporting the old values. The `c200-control-sync` background service watches for that and reapplies your saved settings within about a second, so OBS, browsers and calling apps get the same view as the preview. `./install.sh` installs and starts it.

```bash
systemctl --user status c200-control-sync
```

## Frame rate in low light

In dim light the C200's auto exposure lengthens each frame, dropping from 30 fps to about 13 fps, which looks laggy and grainy. More light on your face fixes both.

The app leaves exposure on auto and has no manual exposure control. The C200's firmware lists manual as its only exposure mode, so once anything switches it to manual, V4L2 cannot switch it back to auto, and the camera keeps that mode even after you unplug it.

In OBS, turn off Use Buffering in the Video Capture Device properties. With buffering on, OBS holds camera frames back to smooth their timing, which adds visible delay.

## Requirements

- Python 3 with PyGObject
- GTK 4 and libadwaita
- `v4l2-ctl`
- GStreamer with its V4L2, JPEG, H.264, and appsink plugins

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

The installer adds `C200 Control` to the standard application launcher and enables the settings sync service. To uninstall, run `systemctl --user disable --now c200-control-sync` and remove `~/.local/share/applications/c200-control.desktop` and `~/.config/systemd/user/c200-control-sync.service`.

Settings are stored in `~/.config/c200-control/settings.json` and are not part of this repository.

## Test

```bash
python3 -m unittest discover -s tests -v
```
