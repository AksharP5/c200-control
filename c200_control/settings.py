from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


# The controls the app shows and remembers. Exposure is left out on purpose: the C200's
# firmware lists manual as its only exposure mode, so once switched to manual, V4L2
# cannot switch it back to auto, and the camera keeps that mode across replugging.
CONTROL_GROUPS = (
    (
        "Framing",
        (
            ("zoom_absolute", "Field of view / zoom", "100 is the widest view"),
            ("pan_absolute", "Pan", None),
            ("tilt_absolute", "Tilt", None),
        ),
    ),
    (
        "Image",
        (
            ("brightness", "Brightness", None),
            ("contrast", "Contrast", None),
            ("saturation", "Saturation", None),
            ("sharpness", "Sharpness", None),
            ("gamma", "Gamma", None),
            ("hue", "Hue", None),
        ),
    ),
    (
        "Lighting",
        (
            ("white_balance_automatic", "Auto white balance", None),
            ("white_balance_temperature", "White balance", None),
            ("power_line_frequency", "Anti-flicker", None),
        ),
    ),
    (
        "Focus",
        (
            ("focus_automatic_continuous", "Autofocus", None),
            ("focus_absolute", "Manual focus", None),
        ),
    ),
)
SAVED_CONTROLS = frozenset(name for _title, rows in CONTROL_GROUPS for name, _label, _note in rows)

CONFIG_PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "c200-control" / "settings.json"


class SettingsStore:
    def load(self) -> dict[str, Any]:
        try:
            data = json.loads(CONFIG_PATH.read_text())
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def saved_controls(self) -> dict[str, int]:
        saved = self.load().get("controls", {})
        if not isinstance(saved, dict):
            return {}
        return {
            name: value
            for name, value in saved.items()
            if name in SAVED_CONTROLS and isinstance(value, int)
        }

    def save(
        self,
        controls: dict[str, int],
        preview_mode: str | None,
        preview_mirrored: bool,
    ) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = CONFIG_PATH.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "controls": controls,
                    "preview_mode": preview_mode,
                    "preview_mirrored": preview_mirrored,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        temporary_path.replace(CONFIG_PATH)
