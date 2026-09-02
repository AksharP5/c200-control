from types import SimpleNamespace
import unittest

from c200_control.app import C200Window
from c200_control.camera import StreamMode


class FakeScale:
    def __init__(self, value: float):
        self.value = value

    def get_value(self) -> float:
        return self.value

    def set_value(self, value: float) -> None:
        self.value = value


class FakeLabel:
    def __init__(self):
        self.value = ""

    def set_label(self, value: str) -> None:
        self.value = value


class FakeAdjustment:
    def __init__(self):
        self.value = 0.0

    def get_value(self) -> float:
        return self.value

    def set_value(self, value: float) -> None:
        self.value = value

    def get_page_size(self) -> float:
        return 400.0

    def get_lower(self) -> float:
        return 0.0

    def get_upper(self) -> float:
        return 1200.0


class FakeFlip:
    def __init__(self):
        self.direction = 0

    def set_property(self, name: str, value: int) -> None:
        if name == "video-direction":
            self.direction = value


class FakePipeline:
    def __init__(self, flip: FakeFlip):
        self.flip = flip

    def get_by_name(self, name: str) -> FakeFlip | None:
        return self.flip if name == "preview_flip" else None


class ControlInteractionTests(unittest.TestCase):
    def test_preview_modes_include_h264_and_mjpeg(self) -> None:
        modes = [
            StreamMode("MJPG", 1920, 1080, 30),
            StreamMode("H264", 1920, 1080, 60),
            StreamMode("YUYV", 640, 480, 30),
        ]

        selected = C200Window.preferred_modes(None, modes)

        self.assertEqual([mode.pixel_format for mode in selected], ["H264", "MJPG"])

    def test_non_pointer_change_is_reverted(self) -> None:
        state = SimpleNamespace(
            initializing=False,
            adjusting_controls=set(),
            control_values={"zoom_absolute": 250},
        )
        scale = FakeScale(255)

        C200Window.slider_changed(state, scale, "zoom_absolute", FakeLabel(), 1)

        self.assertEqual(scale.value, 250)

    def test_pointer_change_is_applied(self) -> None:
        applied: list[tuple[str, int]] = []
        state = SimpleNamespace(
            initializing=False,
            adjusting_controls={"zoom_absolute"},
            control_values={"zoom_absolute": 250},
            format_value=lambda _name, value: str(value),
            queue_control=lambda name, value: applied.append((name, value)),
        )
        label = FakeLabel()

        C200Window.slider_changed(state, FakeScale(260), "zoom_absolute", label, 1)

        self.assertEqual(label.value, "260")
        self.assertEqual(applied, [("zoom_absolute", 260)])

    def test_wheel_delta_scrolls_the_page(self) -> None:
        adjustment = FakeAdjustment()
        state = SimpleNamespace(
            scroller=SimpleNamespace(get_vadjustment=lambda: adjustment),
        )

        handled = C200Window.scroll_over_scale(state, None, 0, 2)

        self.assertTrue(handled)
        self.assertEqual(adjustment.value, 100)

    def test_mirror_changes_the_running_preview_and_saves(self) -> None:
        flip = FakeFlip()
        saved: list[bool] = []
        state = SimpleNamespace(
            preview_pipeline=FakePipeline(flip),
            preview_mirrored=False,
            save_settings=lambda: saved.append(state.preview_mirrored),
        )
        button = SimpleNamespace(get_active=lambda: True)

        C200Window.preview_mirror_changed(state, button)

        self.assertTrue(state.preview_mirrored)
        self.assertEqual(flip.direction, 4)
        self.assertEqual(saved, [True])


if __name__ == "__main__":
    unittest.main()
