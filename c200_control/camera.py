from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import re
import subprocess


CONTROL_PATTERN = re.compile(
    r"^\s*(?P<name>[a-z0-9_]+)\s+0x[0-9a-f]+\s+"
    r"\((?P<kind>[^)]+)\)\s*:\s*(?P<details>.*)$",
    re.IGNORECASE,
)
MENU_PATTERN = re.compile(r"^\s+(?P<value>-?\d+):\s+(?P<label>.+)$")
FORMAT_PATTERN = re.compile(r"^\s*\[\d+\]:\s+'(?P<format>[A-Z0-9]+)'")
SIZE_PATTERN = re.compile(r"Size:\s+Discrete\s+(?P<width>\d+)x(?P<height>\d+)")
FPS_PATTERN = re.compile(r"\((?P<fps>\d+(?:\.\d+)?)\s+fps\)")


class CameraError(RuntimeError):
    pass


@dataclass(frozen=True)
class CameraDevice:
    name: str
    path: Path


@dataclass(frozen=True)
class CameraControl:
    name: str
    kind: str
    minimum: int | None
    maximum: int | None
    step: int | None
    default: int | None
    value: int | None
    flags: frozenset[str]
    menu: tuple[tuple[int, str], ...] = ()


@dataclass(frozen=True)
class StreamMode:
    pixel_format: str
    width: int
    height: int
    fps: float

    @property
    def key(self) -> str:
        return f"{self.pixel_format}:{self.width}x{self.height}:{self.fps:g}"

    @property
    def label(self) -> str:
        format_name = "MJPEG" if self.pixel_format == "MJPG" else self.pixel_format
        return f"{self.width} x {self.height}  {self.fps:g} fps  {format_name}"

    @property
    def ffmpeg_format(self) -> str:
        return {
            "MJPG": "mjpeg",
            "H264": "h264",
            "YUYV": "yuyv422",
        }.get(self.pixel_format, self.pixel_format.lower())


def _number(details: str, name: str) -> int | None:
    match = re.search(rf"(?:^|\s){re.escape(name)}=(-?\d+)(?:\s|$)", details)
    return int(match.group(1)) if match else None


def parse_controls(output: str) -> dict[str, CameraControl]:
    controls: dict[str, CameraControl] = {}
    current_name: str | None = None

    for line in output.splitlines():
        control_match = CONTROL_PATTERN.match(line)
        if control_match:
            details = control_match.group("details")
            flags_match = re.search(r"(?:^|\s)flags=([a-z0-9,-]+)", details)
            flags = frozenset(flags_match.group(1).split(",")) if flags_match else frozenset()
            current_name = control_match.group("name")
            controls[current_name] = CameraControl(
                name=current_name,
                kind=control_match.group("kind"),
                minimum=_number(details, "min"),
                maximum=_number(details, "max"),
                step=_number(details, "step"),
                default=_number(details, "default"),
                value=_number(details, "value"),
                flags=flags,
            )
            continue

        menu_match = MENU_PATTERN.match(line)
        if not menu_match or current_name is None:
            continue

        control = controls[current_name]
        controls[current_name] = replace(
            control,
            menu=control.menu
            + ((int(menu_match.group("value")), menu_match.group("label").strip()),),
        )

    return controls


def parse_stream_modes(output: str) -> list[StreamMode]:
    modes: list[StreamMode] = []
    pixel_format: str | None = None
    size: tuple[int, int] | None = None

    for line in output.splitlines():
        if format_match := FORMAT_PATTERN.match(line):
            pixel_format = format_match.group("format")
            size = None
            continue

        if size_match := SIZE_PATTERN.search(line):
            size = (int(size_match.group("width")), int(size_match.group("height")))
            continue

        fps_match = FPS_PATTERN.search(line)
        if not fps_match or pixel_format is None or size is None:
            continue

        mode = StreamMode(pixel_format, *size, float(fps_match.group("fps")))
        if mode not in modes:
            modes.append(mode)

    return modes


def parse_devices(output: str) -> list[CameraDevice]:
    devices: list[CameraDevice] = []
    current_name: str | None = None

    for line in output.splitlines():
        if line and not line[0].isspace() and line.rstrip().endswith(":"):
            current_name = line.rstrip()[:-1]
            continue

        path = line.strip()
        if current_name and path.startswith("/dev/video"):
            devices.append(CameraDevice(current_name, Path(path)))

    return devices


def applicable_control_values(
    controls: dict[str, CameraControl],
    current_values: dict[str, int],
    values: dict[str, int],
) -> dict[str, int]:
    state = current_values | values
    automatic_controls = (
        "white_balance_automatic",
        "focus_automatic_continuous",
        "auto_exposure",
    )
    ordered = {name: values[name] for name in automatic_controls if name in values}

    for name, value in values.items():
        control = controls.get(name)
        if name in ordered or control is None or "read-only" in control.flags:
            continue
        if name == "white_balance_temperature" and state.get("white_balance_automatic") != 0:
            continue
        if name == "focus_absolute" and state.get("focus_automatic_continuous") != 0:
            continue
        if name == "exposure_time_absolute" and state.get("auto_exposure") != 1:
            continue
        ordered[name] = value

    return ordered


def run_command(command: list[str], timeout: float = 5) -> str:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CameraError(str(error)) from error

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "Command failed"
        raise CameraError(detail)

    return result.stdout


def find_c200() -> CameraDevice | None:
    try:
        devices = parse_devices(run_command(["v4l2-ctl", "--list-devices"]))
    except CameraError:
        return None

    matches = [device for device in devices if "PowerConf C200" in device.name]
    for device in matches:
        try:
            run_command(["v4l2-ctl", "--device", str(device.path), "--get-fmt-video"])
        except CameraError:
            continue
        return device

    return None


class Camera:
    def __init__(self, device: CameraDevice):
        self.device = device

    def controls(self) -> dict[str, CameraControl]:
        output = run_command(
            ["v4l2-ctl", "--device", str(self.device.path), "--list-ctrls-menus"]
        )
        return parse_controls(output)

    def stream_modes(self) -> list[StreamMode]:
        output = run_command(
            ["v4l2-ctl", "--device", str(self.device.path), "--list-formats-ext"]
        )
        return parse_stream_modes(output)

    def set_controls(self, values: dict[str, int]) -> None:
        if not values:
            return

        assignments = ",".join(f"{name}={value}" for name, value in values.items())
        run_command(
            [
                "v4l2-ctl",
                "--device",
                str(self.device.path),
                f"--set-ctrl={assignments}",
            ]
        )
