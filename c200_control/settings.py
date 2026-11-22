from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


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
        return {name: value for name, value in saved.items() if isinstance(value, int)}

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
