from types import SimpleNamespace
import unittest

from c200_control.app import C200Window


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


class ControlInteractionTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
