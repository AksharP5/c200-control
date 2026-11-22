from pathlib import Path
import tempfile
import unittest

from c200_control.camera import CameraDevice
from c200_control.sync import streaming_interface


def write_interface(usb_device: Path, number: int, interface_class: str, subclass: str) -> Path:
    interface = usb_device / f"{usb_device.name}:1.{number}"
    interface.mkdir()
    (interface / "bInterfaceClass").write_text(f"{interface_class}\n")
    (interface / "bInterfaceSubClass").write_text(f"{subclass}\n")
    return interface


class StreamingInterfaceTests(unittest.TestCase):
    def test_finds_video_streaming_not_audio_streaming(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sysfs = Path(directory)
            usb_device = sysfs / "devices/usb1/1-7"
            usb_device.mkdir(parents=True)
            control = write_interface(usb_device, 0, "0e", "01")
            video_streaming = write_interface(usb_device, 1, "0e", "02")
            write_interface(usb_device, 3, "01", "02")
            video_node = sysfs / "class/video4linux/video0"
            video_node.mkdir(parents=True)
            (video_node / "device").symlink_to(control)

            found = streaming_interface(CameraDevice("C200", Path("/dev/video0")), sysfs)

            self.assertEqual(found, video_streaming.resolve())
