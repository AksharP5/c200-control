"""Re-apply saved settings whenever any app starts streaming from the C200.

The camera resets its image pipeline (zoom included) when a stream starts, but
keeps reporting the old control values, so settings applied while idle are lost.
The USB video streaming interface switches to a non-zero alternate setting while
video flows, which gives a cheap, root-free signal for "a stream just started".
"""

from __future__ import annotations

from pathlib import Path
import sys
import time

from .camera import Camera, CameraDevice, CameraError, applicable_control_values, find_c200
from .settings import SettingsStore


POLL_SECONDS = 0.25
RECONNECT_SECONDS = 2
USB_VIDEO_CLASS = "0e"
USB_VIDEO_STREAMING = "02"


def streaming_interface(device: CameraDevice, sysfs: Path = Path("/sys")) -> Path | None:
    control_interface = (sysfs / "class/video4linux" / device.path.name / "device").resolve()
    usb_device = control_interface.parent
    for interface in sorted(usb_device.glob(f"{usb_device.name}:*")):
        try:
            if (
                (interface / "bInterfaceClass").read_text().strip() == USB_VIDEO_CLASS
                and (interface / "bInterfaceSubClass").read_text().strip() == USB_VIDEO_STREAMING
            ):
                return interface
        except OSError:
            continue
    return None


def apply_saved_controls(camera: Camera, store: SettingsStore) -> None:
    controls = camera.controls()
    current = {name: control.value for name, control in controls.items() if control.value is not None}
    saved = {name: value for name, value in store.saved_controls().items() if name in controls}
    camera.set_controls(applicable_control_values(controls, current, saved))


def follow(device: CameraDevice, store: SettingsStore) -> None:
    interface = streaming_interface(device)
    if interface is None:
        print(f"No video streaming interface found for {device.path}", file=sys.stderr)
        return

    camera = Camera(device)
    alternate_setting = interface / "bAlternateSetting"
    was_streaming = False
    while True:
        try:
            streaming = alternate_setting.read_text().strip() != "0"
        except OSError:
            return
        if streaming and not was_streaming:
            try:
                apply_saved_controls(camera, store)
            except CameraError as error:
                print(f"Could not apply saved settings: {error}", file=sys.stderr)
        was_streaming = streaming
        time.sleep(POLL_SECONDS)


def main() -> int:
    store = SettingsStore()
    while True:
        device = find_c200()
        if device is not None:
            follow(device, store)
        time.sleep(RECONNECT_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
