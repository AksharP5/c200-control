from __future__ import annotations

import argparse
from fractions import Fraction
import json
import os
from pathlib import Path
import sys
from typing import Any

import gi

gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("Gst", "1.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gst, Gtk  # noqa: E402

from .camera import (
    Camera,
    CameraControl,
    CameraError,
    StreamMode,
    applicable_control_values,
    find_c200,
)


APP_ID = "com.akshar.C200Control"
CONFIG_PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "c200-control" / "settings.json"
Gst.init(None)

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
            ("auto_exposure", "Manual exposure", None),
            ("exposure_time_absolute", "Exposure time", None),
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


class SettingsStore:
    def load(self) -> dict[str, Any]:
        try:
            data = json.loads(CONFIG_PATH.read_text())
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def save(self, controls: dict[str, int], preview_mode: str | None) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = CONFIG_PATH.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(
                {"version": 1, "controls": controls, "preview_mode": preview_mode},
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        temporary_path.replace(CONFIG_PATH)


class C200Window(Adw.ApplicationWindow):
    def __init__(self, application: Adw.Application):
        super().__init__(application=application, title="C200 Control")
        self.set_default_size(620, 760)
        self.set_size_request(460, 560)

        self.store = SettingsStore()
        self.camera: Camera | None = None
        self.controls: dict[str, CameraControl] = {}
        self.control_values: dict[str, int] = {}
        self.control_widgets: dict[str, Gtk.Widget] = {}
        self.stream_modes: list[StreamMode] = []
        self.pending_values: dict[str, int] = {}
        self.pending_source: int | None = None
        self.preview_pipeline: Gst.Element | None = None
        self.preview_bus: Gst.Bus | None = None
        self.preview_generation = 0
        self.pending_frame: tuple[int, bytes, int, int] | None = None
        self.frame_update_scheduled = False
        self.initializing = False

        self.toast_overlay = Adw.ToastOverlay()
        toolbar_view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.window_title = Adw.WindowTitle(title="C200 Control", subtitle="Anker PowerConf C200")
        header.set_title_widget(self.window_title)

        refresh_button = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh_button.set_tooltip_text("Reconnect camera")
        refresh_button.connect("clicked", lambda _button: self.load_camera())
        header.pack_end(refresh_button)

        toolbar_view.add_top_bar(header)
        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        self.content.set_margin_top(24)
        self.content.set_margin_bottom(24)
        self.content.set_margin_start(24)
        self.content.set_margin_end(24)

        self.scroller = Gtk.ScrolledWindow()
        self.scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroller.set_child(self.content)
        toolbar_view.set_content(self.scroller)
        self.toast_overlay.set_child(toolbar_view)
        self.set_content(self.toast_overlay)
        self.connect("close-request", self.on_close_request)

        self.load_camera()

    def clear_content(self) -> None:
        while child := self.content.get_first_child():
            self.content.remove(child)
        self.control_widgets.clear()

    def load_camera(self) -> None:
        self.stop_preview()
        self.clear_content()
        device = find_c200()
        if device is None:
            self.camera = None
            self.window_title.set_subtitle("Camera disconnected")
            self.build_disconnected_view()
            return

        self.camera = Camera(device)
        try:
            self.controls = self.camera.controls()
            self.stream_modes = self.preferred_modes(self.camera.stream_modes())
        except CameraError as error:
            self.camera = None
            self.window_title.set_subtitle("Camera unavailable")
            self.build_error_view(str(error))
            return

        self.control_values = {
            name: control.value
            for name, control in self.controls.items()
            if control.value is not None
        }
        self.window_title.set_subtitle(f"Connected at {device.path}")
        self.apply_saved_controls()
        self.reload_values()
        self.build_connected_view()

    def apply_saved_controls(self) -> None:
        if self.camera is None:
            return
        saved = self.store.load().get("controls", {})
        if not isinstance(saved, dict):
            return

        values = {
            name: value
            for name, value in saved.items()
            if name in self.controls and isinstance(value, int)
        }
        if not values:
            return

        try:
            self.camera.set_controls(
                applicable_control_values(self.controls, self.control_values, values)
            )
        except CameraError:
            return

    def reload_values(self) -> None:
        if self.camera is None:
            return
        try:
            self.controls = self.camera.controls()
        except CameraError:
            return
        self.control_values = {
            name: control.value
            for name, control in self.controls.items()
            if control.value is not None
        }

    def build_disconnected_view(self) -> None:
        self.content.append(self.status_view("camera-disabled-symbolic", "C200 not found", "Connect the camera, then refresh."))

    def build_error_view(self, message: str) -> None:
        self.content.append(self.status_view("dialog-error-symbolic", "Camera unavailable", message))

    def status_view(self, icon_name: str, title: str, detail: str) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_valign(Gtk.Align.CENTER)
        box.set_vexpand(True)

        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(56)
        icon.add_css_class("dim-label")
        box.append(icon)

        title_label = Gtk.Label(label=title)
        title_label.add_css_class("title-2")
        box.append(title_label)

        detail_label = Gtk.Label(label=detail)
        detail_label.set_wrap(True)
        detail_label.set_justify(Gtk.Justification.CENTER)
        detail_label.add_css_class("dim-label")
        box.append(detail_label)
        return box

    def build_connected_view(self) -> None:
        self.content.append(self.build_preview_section())

        for title, definitions in CONTROL_GROUPS:
            rows = [definition for definition in definitions if definition[0] in self.controls]
            if not rows:
                continue

            section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            heading = Gtk.Label(label=title, xalign=0)
            heading.add_css_class("title-4")
            section.append(heading)

            for index, (name, label, note) in enumerate(rows):
                section.append(self.build_control(name, label, note))
                if index < len(rows) - 1:
                    section.append(Gtk.Separator())

            self.content.append(section)

        reset_button = Gtk.Button(label="Restore camera defaults")
        reset_button.add_css_class("destructive-action")
        reset_button.set_halign(Gtk.Align.START)
        reset_button.connect("clicked", self.restore_defaults)
        self.content.append(reset_button)
        self.refresh_dependencies()
        GLib.idle_add(self.start_preview)

    def build_preview_section(self) -> Gtk.Widget:
        section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        heading_row = Gtk.Box(spacing=12)
        heading = Gtk.Label(label="Live preview", xalign=0)
        heading.add_css_class("title-4")
        heading.set_hexpand(True)
        heading_row.append(heading)

        self.preview_status = Gtk.Label(label="Starting")
        self.preview_status.add_css_class("dim-label")
        heading_row.append(self.preview_status)
        section.append(heading_row)

        overlay = Gtk.Overlay()
        overlay.set_overflow(Gtk.Overflow.HIDDEN)
        overlay.add_css_class("view")

        self.preview_picture = Gtk.Picture()
        self.preview_picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.preview_picture.set_can_shrink(True)
        self.preview_picture.set_hexpand(True)
        self.preview_picture.set_vexpand(True)
        overlay.set_child(self.preview_picture)

        self.preview_message = Gtk.Label(label="Starting preview...")
        self.preview_message.add_css_class("dim-label")
        self.preview_message.set_halign(Gtk.Align.CENTER)
        self.preview_message.set_valign(Gtk.Align.CENTER)
        overlay.add_overlay(self.preview_message)

        aspect_frame = Gtk.AspectFrame.new(0.5, 0.5, 16 / 9, False)
        aspect_frame.set_child(overlay)
        aspect_frame.set_size_request(-1, 280)
        section.append(aspect_frame)

        row = Gtk.Box(spacing=12)
        row.set_hexpand(True)
        labels = [mode.label for mode in self.stream_modes] or ["640 x 480  30 fps"]
        self.mode_dropdown = Gtk.DropDown.new_from_strings(labels)
        self.mode_dropdown.set_hexpand(True)

        saved_mode = self.store.load().get("preview_mode")
        selected = next(
            (index for index, mode in enumerate(self.stream_modes) if mode.key == saved_mode),
            next((index for index, mode in enumerate(self.stream_modes) if mode.width == 1280 and mode.height == 720), 0),
        )
        self.mode_dropdown.set_selected(selected)
        self.mode_dropdown.connect("notify::selected", self.preview_mode_changed)
        row.append(self.mode_dropdown)

        self.preview_button = Gtk.Button(label="Pause preview")
        self.preview_button.connect("clicked", self.toggle_preview)
        row.append(self.preview_button)
        section.append(row)

        note = Gtk.Label(
            label="This mode controls the preview. Calling apps choose their own resolution and frame rate.",
            xalign=0,
        )
        note.set_wrap(True)
        note.add_css_class("dim-label")
        note.add_css_class("caption")
        section.append(note)
        return section

    def build_control(self, name: str, label_text: str, note: str | None) -> Gtk.Widget:
        control = self.controls[name]
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        header = Gtk.Box(spacing=12)
        label_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        label = Gtk.Label(label=label_text, xalign=0)
        label_box.append(label)
        if note:
            note_label = Gtk.Label(label=note, xalign=0)
            note_label.add_css_class("caption")
            note_label.add_css_class("dim-label")
            label_box.append(note_label)
        header.append(label_box)

        if control.kind == "bool" or name == "auto_exposure":
            switch = Gtk.Switch()
            switch.set_valign(Gtk.Align.CENTER)
            switch.set_halign(Gtk.Align.END)
            switch.set_hexpand(True)
            active = control.value == (1 if name == "auto_exposure" else 1)
            switch.set_active(active)
            switch.connect("notify::active", self.boolean_changed, name)
            header.append(switch)
            row.append(header)
            self.control_widgets[name] = switch
            return row

        if control.kind == "menu" and control.menu:
            values = [value for value, _label in control.menu]
            dropdown = Gtk.DropDown.new_from_strings([label for _value, label in control.menu])
            dropdown.set_halign(Gtk.Align.END)
            dropdown.set_hexpand(True)
            selected = values.index(control.value) if control.value in values else 0
            dropdown.set_selected(selected)
            dropdown.connect("notify::selected", self.menu_changed, name, values)
            header.append(dropdown)
            row.append(header)
            self.control_widgets[name] = dropdown
            return row

        if control.minimum is None or control.maximum is None or control.value is None:
            unavailable = Gtk.Label(label="Unavailable")
            unavailable.add_css_class("dim-label")
            unavailable.set_hexpand(True)
            unavailable.set_halign(Gtk.Align.END)
            header.append(unavailable)
            row.append(header)
            return row

        value_label = Gtk.Label(label=self.format_value(name, control.value))
        value_label.add_css_class("numeric")
        value_label.set_hexpand(True)
        value_label.set_halign(Gtk.Align.END)
        header.append(value_label)
        row.append(header)

        step = control.step or 1
        adjustment = Gtk.Adjustment(
            value=control.value,
            lower=control.minimum,
            upper=control.maximum,
            step_increment=step,
            page_increment=max(step, (control.maximum - control.minimum) / 10),
        )
        scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adjustment)
        scale.set_draw_value(False)
        scale.set_hexpand(True)
        if control.default is not None and control.minimum <= control.default <= control.maximum:
            scale.add_mark(control.default, Gtk.PositionType.BOTTOM, None)
        scale.connect("value-changed", self.slider_changed, name, value_label, step)
        scroll_controller = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.BOTH_AXES)
        scroll_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        scroll_controller.connect("scroll", self.scroll_over_scale)
        scale.add_controller(scroll_controller)
        row.append(scale)
        self.control_widgets[name] = scale
        return row

    def format_value(self, name: str, value: int) -> str:
        if name == "zoom_absolute":
            return f"{value / 100:.2f}x"
        if name in {"pan_absolute", "tilt_absolute"}:
            return f"{value / 3600:g} degrees"
        if name == "white_balance_temperature":
            return f"{value} K"
        if name == "exposure_time_absolute":
            return f"{value / 10:g} ms"
        return str(value)

    def slider_changed(self, scale: Gtk.Scale, name: str, label: Gtk.Label, step: int) -> None:
        if self.initializing:
            return
        value = round(scale.get_value() / step) * step
        label.set_label(self.format_value(name, value))
        self.queue_control(name, value)

    def boolean_changed(self, switch: Gtk.Switch, _property: Any, name: str) -> None:
        if self.initializing:
            return
        value = 1 if switch.get_active() else 0
        self.queue_control(name, value)
        self.refresh_dependencies()

    def menu_changed(
        self,
        dropdown: Gtk.DropDown,
        _property: Any,
        name: str,
        values: list[int],
    ) -> None:
        if self.initializing:
            return
        selected = dropdown.get_selected()
        if selected < len(values):
            self.queue_control(name, values[selected])

    def queue_control(self, name: str, value: int) -> None:
        self.pending_values[name] = value
        self.control_values[name] = value
        if self.pending_source is not None:
            GLib.source_remove(self.pending_source)
        self.pending_source = GLib.timeout_add(120, self.flush_controls)

    def flush_controls(self) -> bool:
        self.pending_source = None
        if self.camera is None or not self.pending_values:
            return GLib.SOURCE_REMOVE

        values = self.pending_values
        self.pending_values = {}
        try:
            self.camera.set_controls(
                applicable_control_values(self.controls, self.control_values, values)
            )
        except CameraError as error:
            self.show_toast(f"Could not apply setting: {error}")
            return GLib.SOURCE_REMOVE

        self.save_settings()
        return GLib.SOURCE_REMOVE

    def refresh_dependencies(self) -> None:
        dependencies = (
            ("white_balance_temperature", "white_balance_automatic", False),
            ("focus_absolute", "focus_automatic_continuous", False),
            ("exposure_time_absolute", "auto_exposure", True),
        )
        for child_name, parent_name, active_when_parent_on in dependencies:
            child = self.control_widgets.get(child_name)
            parent = self.control_widgets.get(parent_name)
            if child is None or not isinstance(parent, Gtk.Switch):
                continue
            child.set_sensitive(parent.get_active() is active_when_parent_on)

    def preview_mode_changed(self, _dropdown: Gtk.DropDown, _property: Any) -> None:
        self.save_settings()
        if self.preview_pipeline is not None:
            self.stop_preview()
            GLib.idle_add(self.start_preview)

    def scroll_over_scale(
        self,
        _controller: Gtk.EventControllerScroll,
        delta_x: float,
        delta_y: float,
    ) -> bool:
        adjustment = self.scroller.get_vadjustment()
        delta = delta_y if delta_y else delta_x
        step = max(36, adjustment.get_page_size() / 8)
        next_value = adjustment.get_value() + delta * step
        maximum = max(adjustment.get_lower(), adjustment.get_upper() - adjustment.get_page_size())
        adjustment.set_value(min(maximum, max(adjustment.get_lower(), next_value)))
        return True

    def selected_mode(self) -> StreamMode | None:
        selected = self.mode_dropdown.get_selected()
        return self.stream_modes[selected] if selected < len(self.stream_modes) else None

    def save_settings(self) -> None:
        mode = self.selected_mode()
        try:
            self.store.save(self.control_values, mode.key if mode else None)
        except OSError as error:
            self.show_toast(f"Could not save settings: {error}")

    def toggle_preview(self, _button: Gtk.Button) -> None:
        if self.preview_pipeline is not None:
            self.stop_preview()
            return
        self.start_preview()

    def start_preview(self) -> bool:
        if self.camera is None:
            self.show_toast("Connect the C200 first")
            return GLib.SOURCE_REMOVE
        mode = self.selected_mode()
        if mode is None:
            self.show_toast("No supported preview mode found")
            return GLib.SOURCE_REMOVE

        fps = Fraction(str(mode.fps)).limit_denominator(1001)
        scale = min(1, 1280 / mode.width, 720 / mode.height)
        output_width = max(2, round(mode.width * scale / 2) * 2)
        output_height = max(2, round(mode.height * scale / 2) * 2)
        pipeline_description = (
            f"v4l2src device={self.camera.device.path} do-timestamp=true ! "
            f"image/jpeg,width={mode.width},height={mode.height},"
            f"framerate={fps.numerator}/{fps.denominator} ! "
            "queue max-size-buffers=1 leaky=downstream ! "
            "jpegdec ! videoconvert ! videoscale ! "
            f"video/x-raw,format=RGB,width={output_width},height={output_height} ! "
            "appsink name=preview_sink emit-signals=true max-buffers=1 drop=true sync=false"
        )
        try:
            pipeline = Gst.parse_launch(pipeline_description)
        except GLib.Error as error:
            self.show_toast(f"Could not open preview: {error}")
            self.preview_message.set_label("Preview unavailable")
            self.preview_message.set_visible(True)
            self.preview_status.set_label("Unavailable")
            self.preview_button.set_label("Retry preview")
            return GLib.SOURCE_REMOVE

        sink = pipeline.get_by_name("preview_sink")
        if sink is None:
            self.show_toast("Could not create preview output")
            return GLib.SOURCE_REMOVE

        self.preview_generation += 1
        sink.connect("new-sample", self.new_preview_sample, self.preview_generation)
        self.preview_pipeline = pipeline
        self.preview_bus = pipeline.get_bus()
        self.preview_bus.add_signal_watch()
        self.preview_bus.connect("message", self.preview_message_received, pipeline)

        self.preview_message.set_label("Starting preview...")
        self.preview_message.set_visible(True)
        self.preview_status.set_label("Starting")
        self.preview_button.set_label("Pause preview")
        if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            self.preview_failed("The camera could not start")
        return GLib.SOURCE_REMOVE

    def new_preview_sample(
        self,
        sink: Gst.Element,
        generation: int,
    ) -> Gst.FlowReturn:
        sample = sink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.ERROR

        caps = sample.get_caps()
        structure = caps.get_structure(0)
        width = structure.get_value("width")
        height = structure.get_value("height")
        buffer = sample.get_buffer()
        success, mapping = buffer.map(Gst.MapFlags.READ)
        if not success:
            return Gst.FlowReturn.ERROR
        try:
            data = bytes(mapping.data)
        finally:
            buffer.unmap(mapping)

        self.pending_frame = (generation, data, width, height)
        if not self.frame_update_scheduled:
            self.frame_update_scheduled = True
            GLib.idle_add(self.display_pending_frame)
        return Gst.FlowReturn.OK

    def display_pending_frame(self) -> bool:
        frame = self.pending_frame
        self.pending_frame = None
        self.frame_update_scheduled = False
        if frame is None:
            return GLib.SOURCE_REMOVE

        generation, data, width, height = frame
        if generation != self.preview_generation:
            return GLib.SOURCE_REMOVE

        texture = Gdk.MemoryTexture.new(
            width,
            height,
            Gdk.MemoryFormat.R8G8B8,
            GLib.Bytes.new(data),
            width * 3,
        )
        self.preview_picture.set_paintable(texture)
        self.preview_message.set_visible(False)
        self.preview_status.set_label("Live")
        return GLib.SOURCE_REMOVE

    def preview_message_received(
        self,
        _bus: Gst.Bus,
        message: Gst.Message,
        pipeline: Gst.Element,
    ) -> None:
        if pipeline is not self.preview_pipeline:
            return
        if message.type == Gst.MessageType.ERROR:
            error, _debug = message.parse_error()
            self.preview_failed(error.message)

    def preview_failed(self, message: str) -> None:
        self.stop_preview()
        self.preview_message.set_label("Preview unavailable")
        self.preview_message.set_visible(True)
        self.preview_status.set_label("Unavailable")
        self.preview_button.set_label("Retry preview")
        self.show_toast(message)

    def stop_preview(self) -> None:
        self.preview_generation += 1
        self.pending_frame = None
        if self.preview_bus is not None:
            self.preview_bus.remove_signal_watch()
            self.preview_bus = None
        if self.preview_pipeline is not None:
            self.preview_pipeline.set_state(Gst.State.NULL)
            self.preview_pipeline = None
        if hasattr(self, "preview_button"):
            self.preview_button.set_label("Resume preview")
        if hasattr(self, "preview_status"):
            self.preview_status.set_label("Paused")
        if hasattr(self, "preview_message"):
            self.preview_message.set_label("Preview paused")
            self.preview_message.set_visible(True)

    def restore_defaults(self, _button: Gtk.Button) -> None:
        if self.camera is None:
            return

        defaults = {
            name: control.default
            for name, control in self.controls.items()
            if control.default is not None
        }
        try:
            self.camera.set_controls(
                applicable_control_values(self.controls, self.control_values, defaults)
            )
        except CameraError as error:
            self.show_toast(f"Could not restore defaults: {error}")
            return

        self.store.save({}, self.selected_mode().key if self.selected_mode() else None)
        self.show_toast("Camera defaults restored")
        self.load_camera()

    def preferred_modes(self, modes: list[StreamMode]) -> list[StreamMode]:
        mjpeg_modes = [mode for mode in modes if mode.pixel_format == "MJPG" and mode.fps <= 30]
        selected = mjpeg_modes or modes
        return sorted(selected, key=lambda mode: (mode.width * mode.height, mode.fps), reverse=True)

    def show_toast(self, message: str) -> None:
        self.toast_overlay.add_toast(Adw.Toast(title=message, timeout=4))

    def on_close_request(self, _window: Gtk.Window) -> bool:
        if self.pending_source is not None:
            GLib.source_remove(self.pending_source)
            self.flush_controls()
        self.stop_preview()
        return False


class C200Application(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.window: C200Window | None = None

    def do_activate(self) -> None:
        if self.window is None:
            self.window = C200Window(self)
        self.window.present()


def check_camera() -> int:
    device = find_c200()
    if device is None:
        print("C200 not found")
        return 1

    camera = Camera(device)
    try:
        controls = camera.controls()
        modes = camera.stream_modes()
    except CameraError as error:
        print(f"C200 found at {device.path}, but it is unavailable: {error}")
        return 1

    mjpeg_modes = [mode for mode in modes if mode.pixel_format == "MJPG"]
    print(f"C200 connected at {device.path}")
    print(f"{len(controls)} controls available")
    print(f"{len(mjpeg_modes)} MJPEG preview modes available")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Control an Anker PowerConf C200")
    parser.add_argument("--check", action="store_true", help="check camera availability without opening the UI")
    arguments, gtk_arguments = parser.parse_known_args(argv)
    if arguments.check:
        return check_camera()

    application = C200Application()
    return application.run([sys.argv[0], *gtk_arguments])
