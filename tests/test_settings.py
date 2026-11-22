import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from c200_control import settings


class SavedControlsTests(unittest.TestCase):
    def test_ignores_exposure_left_in_older_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(json.dumps({"controls": {
                "auto_exposure": 1,
                "exposure_time_absolute": 5,
                "zoom_absolute": 400,
            }}))

            with mock.patch.object(settings, "CONFIG_PATH", path):
                saved = settings.SettingsStore().saved_controls()

        self.assertEqual(saved, {"zoom_absolute": 400})


if __name__ == "__main__":
    unittest.main()
