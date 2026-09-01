from pathlib import Path
import unittest

from c200_control.camera import (
    applicable_control_values,
    parse_controls,
    parse_devices,
    parse_stream_modes,
)


CONTROLS = """
User Controls

                     brightness 0x00980900 (int)    : min=0 max=100 step=1 default=50 value=61 flags=has-min-max
        white_balance_automatic 0x0098090c (bool)   : default=1 value=1

Camera Controls

                  auto_exposure 0x009a0901 (menu)   : min=0 max=3 default=0 value=1
                                1: Manual Mode
         exposure_time_absolute 0x009a0902 (int)    : min=1 max=1000 step=1 default=156 value=156 flags=has-min-max
                  zoom_absolute 0x009a090d (int)    : min=100 max=400 step=1 default=100 value=175 flags=has-min-max
"""

MODES = """
    [0]: 'MJPG' (Motion-JPEG, compressed)
        Size: Discrete 2560x1440
            Interval: Discrete 0.033s (30.000 fps)
        Size: Discrete 1280x720
            Interval: Discrete 0.033s (30.000 fps)
    [1]: 'YUYV' (YUYV 4:2:2)
        Size: Discrete 640x480
            Interval: Discrete 0.033s (30.000 fps)
"""

DEVICES = """
Anker PowerConf C200: Anker Pow (usb-0000:00:14.0-7):
    /dev/video0
    /dev/video1
    /dev/media0

Other Camera:
    /dev/video4
"""


class CameraParsingTests(unittest.TestCase):
    def test_parses_controls_and_menu_values(self) -> None:
        controls = parse_controls(CONTROLS)

        self.assertEqual(controls["brightness"].value, 61)
        self.assertEqual(controls["zoom_absolute"].minimum, 100)
        self.assertEqual(controls["auto_exposure"].menu, ((1, "Manual Mode"),))

    def test_parses_only_valid_stream_combinations(self) -> None:
        modes = parse_stream_modes(MODES)

        self.assertEqual(len(modes), 3)
        self.assertEqual(modes[0].key, "MJPG:2560x1440:30")
        self.assertEqual(modes[-1].pixel_format, "YUYV")

    def test_groups_video_nodes_under_device_names(self) -> None:
        devices = parse_devices(DEVICES)

        self.assertEqual(devices[0].name, "Anker PowerConf C200: Anker Pow (usb-0000:00:14.0-7)")
        self.assertEqual(devices[0].path, Path("/dev/video0"))
        self.assertEqual(devices[-1].path, Path("/dev/video4"))

    def test_skips_manual_values_while_automatic_control_is_active(self) -> None:
        controls = parse_controls(CONTROLS)
        current = {"auto_exposure": 0, "exposure_time_absolute": 156}

        automatic = applicable_control_values(
            controls,
            current,
            {"auto_exposure": 0, "exposure_time_absolute": 200},
        )
        manual = applicable_control_values(
            controls,
            current,
            {"auto_exposure": 1, "exposure_time_absolute": 200},
        )

        self.assertEqual(automatic, {"auto_exposure": 0})
        self.assertEqual(manual, {"auto_exposure": 1, "exposure_time_absolute": 200})


if __name__ == "__main__":
    unittest.main()
