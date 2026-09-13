"""Real Tk shell/adapter tests. Run explicitly on a desktop-enabled build."""

import gc
import json
import sys
import time
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from pydeskui import Select, Sidebar, Theme

from pydesktools.app import (
    IMAGE_PLUGIN,
    Application,
    ApplicationConfig,
    application_tokens,
    create_application,
)
from pydesktools.ui import ImageCompressorView, _format_bytes


@pytest.fixture(autouse=True)
def collect_tk_objects_on_owner_thread():
    gc.collect()
    yield
    gc.collect()


def wait(app, predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.root.update()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("GUI did not settle")


def test_light_surfaces_and_binary_size_formatting():
    tokens = application_tokens("light")
    assert {tokens[key] for key in ("background", "card", "popover", "sidebar")} == {
        "#FFFFFF"
    }
    assert _format_bytes(0) == "0 B"
    assert _format_bytes(1023) == "1,023 B"
    assert _format_bytes(1024) == "1.0 KB"
    assert _format_bytes(1023 * 1024) == "1,023.0 KB"
    assert _format_bytes(1024 * 1024) == "1.0 MB"


def test_image_completed_status_replaces_the_disabled_action():
    tk.NoDefaultRoot()
    root = tk.Tk()
    theme = Theme(root)
    view = ImageCompressorView(
        root,
        translate=lambda value: value,
        on_command=lambda _command: None,
        on_preview=lambda: None,
        on_discard=lambda _paths: None,
        on_open_directory=lambda _path: None,
        on_state_change=lambda: None,
        on_drop=lambda _paths: False,
        dnd_available=False,
        theme=theme,
    )
    view.pack(fill="both", expand=True)
    try:
        view.files = ["sample.jpg"]
        view.file_results = {"sample.jpg": {"status": "completed"}}
        view._sync_layout()
        view.sync_compression_action()
        root.update()

        assert view.completed_status.winfo_ismapped()
        assert not view.buttons["compress"].winfo_ismapped()
        assert view.completed_status.cget("text") == "Completed"
        assert view.completed_status.cget("image")

        view.file_results = {}
        view.sync_compression_action()
        root.update()

        assert not view.completed_status.winfo_ismapped()
        assert view.buttons["compress"].winfo_ismapped()
    finally:
        view.destroy()
        theme.close()
        root.destroy()


def test_window_close_hides_when_tray_is_available():
    calls = []
    app = Application.__new__(Application)
    app.closing = False
    app.tray = SimpleNamespace(available=True)
    app.root = SimpleNamespace(withdraw=lambda: calls.append("hide"))
    app.quit = lambda: calls.append("quit")

    app.close()

    assert calls == ["hide"]


def test_window_close_quits_when_platform_has_no_tray():
    calls = []
    app = Application.__new__(Application)
    app.closing = False
    app.tray = SimpleNamespace(available=False)
    app.root = SimpleNamespace(withdraw=lambda: calls.append("hide"))
    app.quit = lambda: calls.append("quit")

    app.close()

    assert calls == ["quit"]


def test_application_flow(tmp_path, monkeypatch):
    tk.NoDefaultRoot()
    monkeypatch.setattr("pydesktools.app.preferred_locale", lambda: "en")
    app = create_application(
        ApplicationConfig(data_dir=tmp_path / "profile", python=Path(sys.executable))
    )
    errors = []
    app.error = errors.append
    try:
        wait(app, lambda: not app.background_busy, timeout=30)
        assert not errors
        app.form.set_values({"text": '{"long":12345678901234567890.0123456789}'})
        app.run_command("format")
        app.navigate("tool", IMAGE_PLUGIN)
        wait(app, lambda: app.task is None)
        app.navigate("tool", "org.pydesk.json-tools")
        assert app.result_artifact
        assert "12345678901234567890.0123456789" in app.detail.text.get("1.0", "end")
        app.run_command("copy")
        wait(app, lambda: app.task is None)
        assert "12345678901234567890.0123456789" in app.root.clipboard_get()
        assert app.toast.is_open
        assert app.toast.label.cget("text") == "Copied to clipboard"
        destination = tmp_path / "导出.json"
        monkeypatch.setattr(
            app.platform,
            "_choose",
            lambda capability, arguments, token, response: response.set_result(str(destination)),
        )
        app.run_command("export")
        wait(app, lambda: app.task is None)
        assert json.loads(destination.read_text())["long"]
        assert app.toast.label.cget("text") == "Exported: 导出.json"
        assert app.json_tool.export_path == destination
        assert app.json_tool.export_status.cget("text") == "Exported: 导出.json"
        assert app.json_tool.export_status.winfo_manager() == "pack"
        assert app.json_tool.reveal_export.winfo_manager() == "pack"
        opened = []
        monkeypatch.setattr("subprocess.Popen", lambda arguments: opened.append(arguments))
        app.json_tool.reveal_export.invoke()
        if sys.platform == "darwin":
            assert opened == [["open", "-R", str(destination)]]
        elif sys.platform == "win32":
            assert opened == [["explorer.exe", "/select,", str(destination)]]
        else:
            assert opened == [["xdg-open", str(destination.parent)]]
        monkeypatch.setattr(
            app.platform,
            "_choose",
            lambda capability, arguments, token, response: response.set_result(None),
        )
        app.run_command("export")
        wait(app, lambda: app.task is None)
        assert app.json_tool.export_path is None
        assert not app.json_tool.export_status.winfo_manager()
        assert not app.json_tool.reveal_export.winfo_manager()
        app.form.set_values({"text": '{"large":"' + "世" * 30000 + '"}'})
        app.run_command("minify")
        assert app.json_tool.export_path is None
        assert not app.json_tool.export_status.winfo_manager()
        assert not app.json_tool.reveal_export.winfo_manager()
        wait(app, lambda: not app.background_busy and app.task is None)
        assert "truncated" in app.detail.text.get("1.0", "end")
        complete = app.services.artifacts.path("org.pydesk.json-tools", app.result_artifact).read_text()
        app.run_command("swap")
        wait(app, lambda: not app.background_busy)
        assert app.json_tool.editor.get("1.0", "end-1c") == complete
        assert app.result_artifact is None
        assert app.json_tool.buttons["copy"].instate(("disabled",))
        raw = '{\r\n    "raw":  true,\r\n "unfinished": '
        imported = tmp_path / "raw.json"
        imported.write_bytes(raw.encode())
        monkeypatch.setattr(app.platform, "_choose",
                            lambda capability, arguments, token, response: response.set_result(str(imported)))
        app.run_command("import")
        wait(app, lambda: app.task is None and not app.background_busy)
        assert app.json_tool.editor.get("1.0", "end-1c") == raw
        assert app.result_artifact is None
        monkeypatch.setattr(app.platform, "_choose",
                            lambda capability, arguments, token, response: response.set_result(None))
        app.run_command("import")
        wait(app, lambda: app.task is None and not app.background_busy)
        assert app.json_tool.editor.get("1.0", "end-1c") == raw
        values = app.form.get_values()
        app.settings.set_mode_preference("dark")
        app.change_theme()
        app.settings.set_language_preference("zh-CN")
        app.change_language()
        assert app.form.get_values() == values
        assert app.theme.mode == "dark"
        assert app.locale == "zh-CN"
        assert not errors
    finally:
        app._close()
        app._shutdown_thread.join(timeout=15)


def test_pydeskui_composition_busy_feedback_and_standalone_navigation(tmp_path, monkeypatch):
    tk.NoDefaultRoot()
    monkeypatch.setattr("pydesktools.app.preferred_locale", lambda: "en")
    app = create_application(
        ApplicationConfig(data_dir=tmp_path / "profile", python=Path(sys.executable))
    )
    try:
        wait(app, lambda: not app.background_busy, timeout=30)
        assert isinstance(app.sidebar, Sidebar)
        assert isinstance(app.settings.language_select, Select)
        assert isinstance(app.settings.mode_select, Select)
        app.root.update()
        assert app.sidebar.winfo_width() == app.theme.px(232)
        assert app.header.winfo_height() == app.theme.px(64)
        assert not hasattr(app, "progress")
        assert app.sidebar.home_button.instate(("selected",))
        assert not any(button.instate(("selected",)) for button in app.sidebar.buttons.values())
        normal_key = next(
            key
            for key in app.theme._image_specs
            if key.endswith(f"navigation.{id(app.sidebar.home_button):x}")
        )
        assert app.theme._image_specs[normal_key][2] is None
        # Theme resources retain both light and dark variants; check the active
        # color rather than whichever cached variant was inserted first.
        assert any(
            spec[2] == app.theme.tokens["sidebar_accent"]
            for key, spec in app.theme._image_specs.items()
            if key.endswith(f"navigation.{id(app.sidebar.home_button):x}.selected")
        )
        assert app.locale_preference == "system"
        assert app.theme_preference == "system"
        sidebar_buttons = dict(app.sidebar.buttons)
        app.refresh()
        assert app.sidebar.buttons == sidebar_buttons
        assert all(app.sidebar.buttons[key] is value for key, value in sidebar_buttons.items())
        app.show_command_palette()
        assert app.palette.is_open
        app.palette_search.insert(0, "json")
        wait(app, lambda: bool(app.palette_results.tree.get_children()))
        app.palette.hide()

        app.form.set_values({"text": '{"quick":true}'})
        app.run_command("format")
        assert app.busy_visible
        assert all(button.instate(("disabled",)) for button in app.command_buttons)
        wait(app, lambda: app.task is None)
        assert not app.busy_visible

        app.task = SimpleNamespace(id="slow-task")
        app._schedule_busy_feedback("format")
        wait(app, lambda: app.busy_visible)
        app.refresh()
        assert not hasattr(app, "progress")
        assert all(button.instate(("disabled",)) for button in app.command_buttons)
        app.task = None
        app._settle_busy_feedback()
        assert not app.busy_visible
        assert not app.command_buttons[0].instate(("disabled",))

        def mapped_sidebars(widget):
            return sum(
                isinstance(child, Sidebar) and child.winfo_ismapped()
                for child in widget.winfo_children()
            ) + sum(mapped_sidebars(child) for child in widget.winfo_children())

        assert mapped_sidebars(app.root) == 1
        app.navigate("plugins")
        app.root.geometry("1100x720")
        app.root.update()
        assert app.workspace_shell.winfo_ismapped() == 0
        assert app.workspace.winfo_ismapped() == 0
        assert app.header.winfo_ismapped() == 0
        assert app.plugins.winfo_ismapped() == 1
        assert mapped_sidebars(app.root) == 0
        assert app.plugins.local_sidebar.winfo_ismapped()
        assert app.plugins.selected_id()
        state_action = (
            app.plugins.disable_button
            if app.plugins.disable_button.winfo_ismapped()
            else app.plugins.enable_button
        )
        visible_actions = [
            app.plugins.install_button,
            state_action,
            app.plugins.uninstall_button,
            app.plugins.delete_button,
        ]
        for button in visible_actions:
            assert button.winfo_ismapped()
            assert button.winfo_width() >= button.winfo_reqwidth()
            assert button.winfo_rootx() + button.winfo_width() <= (
                app.root.winfo_rootx() + app.root.winfo_width()
            )
            assert button.winfo_rooty() + button.winfo_height() <= (
                app.root.winfo_rooty() + app.root.winfo_height()
            )

        app.plugins.filter_control.set("disabled", notify=True)
        app.root.update()
        assert app.plugins.selected_id() is None
        assert not app.plugins.delete_button.winfo_ismapped()
        app.plugins.filter_control.set("all", notify=True)
        app.root.update()
        assert app.plugins.selected_id()
        assert "Content-Type" not in app.plugins.description_label.cget("text")

        def visible_text(widget):
            result = []
            for child in widget.winfo_children():
                try:
                    result.append(str(child.cget("text")))
                except tk.TclError:
                    pass
                result.extend(visible_text(child))
            return result

        app.plugins.home_button.invoke()
        app.root.update()
        assert app.home.winfo_ismapped()
        assert app.header.winfo_ismapped()
        app.navigate("settings")
        app.root.update()
        assert app.plugins.winfo_ismapped() == 0
        assert app.settings.winfo_ismapped() == 1
        assert app.header.winfo_ismapped() == 0
        assert app.workspace_shell.winfo_ismapped() == 0
        assert mapped_sidebars(app.root) == 0
        assert app.settings.local_sidebar.winfo_ismapped()
        assert str(app.services.store.root) in visible_text(app.settings)
        app.settings.set_mode_preference("dark")
        app.change_theme()
        monkeypatch.setattr("pydesktools.app.preferred_theme", lambda root: "light")
        app.settings.set_mode_preference("system")
        app.change_theme()
        assert app.theme.mode == "light"
        if app.root.tk.call("tk", "windowingsystem") == "aqua":
            assert app.root.wm_attributes("-appearance") == "auto"
        app._system_appearance_changed("dark")
        assert app.theme.mode == "dark"
        if app.root.tk.call("tk", "windowingsystem") == "aqua":
            assert app.root.wm_attributes("-appearance") == "auto"
        assert (
            app.theme.style.lookup(
                app.plugins.plugin_list.tree.cget("style"), "background", ("selected",)
            )
            == app.theme.tokens["accent"]
        )
        app.settings.set_mode_preference("light")
        app.change_theme()
        app._system_appearance_changed("dark")
        assert app.theme.mode == "light"

        app.settings.home_button.invoke()
        app.root.update()
        assert app.home.winfo_ismapped()
        assert app.sidebar.winfo_ismapped()

        app.navigate("tool", "org.pydesk.json-tools")
        app.root.update()
        assert app.workspace_shell.winfo_ismapped() == 1
        assert app.header.winfo_ismapped() == 1
        app.json_tool.settings_button.invoke()
        app.root.update()
        assert app.json_tool.options.is_open
        assert app.root.focus_get() is app.json_tool.indent_control
        popup_inset = app.theme.px(max(2, min(app.theme.radius, 6) / 2))
        assert int(app.json_tool.options.content.pack_info()["padx"]) == popup_inset
        assert int(app.json_tool.options.content.pack_info()["pady"]) == popup_inset
        app.root.event_generate("<Return>")
        app.root.update()
        assert not app.json_tool.options.is_open
        app.services.disable("org.pydesk.json-tools")
        app.refresh()
        assert app.current_page == "home"
        assert "org.pydesk.json-tools" not in app.sidebar.buttons
        app._search("json", app.home.results)
        assert not app.home.results.tree.get_children()
    finally:
        app._close()
        app._shutdown_thread.join(timeout=15)


def test_image_compressor_app_flow(tmp_path, monkeypatch):
    tk.NoDefaultRoot()
    monkeypatch.setattr("pydesktools.app.preferred_locale", lambda: "en")
    source = tmp_path / "sample.png"
    Image.new("RGB", (320, 180), "#3b82f6").save(source)
    app = create_application(
        ApplicationConfig(data_dir=tmp_path / "profile", python=Path(sys.executable))
    )
    errors = []
    app.error = errors.append
    try:
        wait(app, lambda: not app.background_busy, timeout=30)

        def choose(capability, arguments, token, response):
            assert capability == "dialogs.open_files"
            value = [str(source)]
            response.set_result(value)

        monkeypatch.setattr(app.platform, "_choose", choose)
        assert not errors
        image_record = app.services.store.get(IMAGE_PLUGIN)
        assert image_record
        assert image_record["manifest"]["version"] == "0.2.2"
        assert "dialogs.choose_directory" not in image_record["manifest"]["capabilities"]
        app.navigate("tool", IMAGE_PLUGIN)
        app.root.update()
        assert app.image_tool.empty_card.winfo_ismapped()
        assert not app.image_tool.toolbar.winfo_ismapped()
        assert not app.image_tool.feedback.winfo_ismapped()
        app.run_command("import_images")
        wait(app, lambda: app.task is None and app.image_tool._photos)
        assert app.image_tool.files == [str(source)], errors
        assert not app.image_tool.empty_card.winfo_ismapped()
        assert app.image_tool.toolbar.winfo_ismapped()
        assert app.image_tool.feedback.winfo_ismapped()
        assert app.image_tool.queue_count.cget("text") == "1 Pending · 1 images selected"
        idle_body_geometry = (
            app.image_tool.body.winfo_y(),
            app.image_tool.body.winfo_height(),
        )
        assert len(app.preview_cache) == 1
        assert app.image_tool._photos
        wait(app, lambda: app.image_tool._preview_resize_job is None)
        photo = app.image_tool._photos[0]
        app.image_tool._render_preview()
        assert app.image_tool._photos[0] is photo
        cached = tuple(app.preview_cache)
        app.request_image_preview()
        assert app.task is None
        assert tuple(app.preview_cache) == cached
        assert not any(item["command_id"] == "preview" for item in app.recent_commands)
        app.image_tool.variables["keep_larger"].set("1")
        wait(app, lambda: app.task is None)
        app.run_command("compress")
        wait(app, lambda: app.task is None)
        assert list(tmp_path.glob("sample-compressed*.jpg"))
        assert source.exists()
        assert app.image_tool.file_results[str(source)]["status"] == "completed"
        assert not app.image_tool.batch_progress.winfo_ismapped()
        assert app.image_tool.result.winfo_ismapped()
        assert (
            app.image_tool.body.winfo_y(),
            app.image_tool.body.winfo_height(),
        ) == idle_body_geometry
        row = app.image_tool.queue.tree.item(str(source))
        assert row["image"]
        assert "Saved" in row["text"]
        assert app.image_tool.buttons["compress"].instate(("disabled",))
        assert app.image_tool.buttons["compress"].cget("text") == "Completed"
        assert not app.image_tool.buttons["compress"].winfo_ismapped()
        assert app.image_tool.completed_status.winfo_ismapped()
        assert app.image_tool.queue_count.cget("text") == "0 Pending · 1 images selected"
        opened = []
        with monkeypatch.context() as patch:
            patch.setattr("subprocess.Popen", lambda arguments: opened.append(arguments))
            app.image_tool.open_output.invoke()
        if sys.platform == "darwin":
            assert opened == [["open", str(tmp_path)]]
        elif sys.platform == "win32":
            assert opened == [["explorer.exe", str(tmp_path)]]
        else:
            assert opened == [["xdg-open", str(tmp_path)]]
        outputs = list(tmp_path.glob("sample-compressed*.jpg"))
        assert app.run_command("compress") is False
        assert list(tmp_path.glob("sample-compressed*.jpg")) == outputs

        added = tmp_path / "added.png"
        Image.new("RGB", (96, 64), "#224466").save(added)
        assert app.run_command("import_images", [str(added)]) is True
        wait(app, lambda: app.task is None and str(added) in app.image_tool.files)
        assert app.image_tool.pending_paths() == [str(added)]
        assert app.image_tool.queue_count.cget("text") == "1 Pending · 2 images selected"
        app.image_tool.set_busy(True)
        assert all(control.instate(("disabled",)) for control in app.image_tool.option_controls)
        assert app.image_tool._drop_enter(None) == "refuse_drop"
        app.image_tool.set_busy(False)
        app.run_command("compress")
        wait(app, lambda: app.task is None)
        assert len(list(tmp_path.glob("sample-compressed*.jpg"))) == 1
        assert len(list(tmp_path.glob("added-compressed*.jpg"))) == 1

        app.image_tool.variables["quality"].set(81)
        app.root.update()
        assert app.image_tool.pending_paths() == [str(source), str(added)]
        assert app.image_tool.buttons["compress"].cget("text") == "Recompress"
        assert app.image_tool.buttons["compress"].winfo_ismapped()
        assert not app.image_tool.completed_status.winfo_ismapped()
        app.run_command("compress")
        wait(app, lambda: app.task is None)
        assert len(list(tmp_path.glob("sample-compressed*.jpg"))) == 2
        assert len(list(tmp_path.glob("added-compressed*.jpg"))) == 2
        quality = app.image_tool.variables["quality"].get()
        app.image_tool.clear_batch()
        app.root.update()
        assert app.image_tool.files == []
        assert app.image_tool.variables["quality"].get() == quality
        assert app.image_tool.empty_card.winfo_ismapped()
        assert len(list(tmp_path.glob("sample-compressed*.jpg"))) == 2
        assert len(list(tmp_path.glob("added-compressed*.jpg"))) == 2

        if app.dnd_available:
            dropped = tmp_path / "拖入 image.png"
            Image.new("RGB", (72, 48), "#446688").save(dropped)
            event = SimpleNamespace(data=app.root.tk.call("list", str(dropped)))
            assert app.image_tool._drop_files(event) == "copy"
            wait(app, lambda: app.task is None and str(dropped) in app.image_tool.files)
            assert app.image_tool.pending_paths() == [str(dropped)]
            app.image_tool.clear_batch()
        app.navigate("settings")
        app.settings.home_button.invoke()
        assert app.current_page == "tool" and app.current_plugin == IMAGE_PLUGIN
        # Rapid selection: the first task is in flight when the desired file changes.
        paths = []
        for index in range(14):
            path = tmp_path / f"cache-{index}.png"
            Image.new("RGB", (80 + index, 80), "#123456").save(path)
            paths.append(str(path))
        app.image_tool.set_files(paths)
        app.image_tool.queue.tree.selection_set(paths[-1])
        app.image_tool.queue._changed()
        wait(app, lambda: app.task is None and not app.image_preview_pending and app.image_tool._photos)
        assert "93 × 80" in app.image_tool.preview_summary.cget("text")
        for path in paths:
            app.image_tool.queue.tree.selection_set(path)
            app.image_tool.queue._changed()
            wait(app, lambda: app.task is None and not app.image_preview_pending and app.image_tool._photos)
        assert len(app.preview_cache) == 12
        preview_records = [r for r in app.services.artifacts.records.values()
                           if r["owner"] == IMAGE_PLUGIN]
        assert len(preview_records) == 24
        assert all(len(r["refs"]) == 1 for r in preview_records)
        assert not errors
    finally:
        app._close()
        app._shutdown_thread.join(timeout=15)


@pytest.mark.skipif(sys.platform != "darwin", reason="Cocoa adapter")
@pytest.mark.parametrize(
    "capability",
    ["dialogs.open_file", "dialogs.open_files", "dialogs.choose_directory"],
)
def test_native_panel_cancel(capability):
    import threading

    from pydesktools_sdk import CancellationToken

    from pydesktools.platform import PlatformAdapter

    root = tk.Tk()
    root.title("PyDesk native cancellation contract")
    root.update()
    adapter = PlatformAdapter(root)
    token = CancellationToken()
    errors = []

    def invoke():
        try:
            adapter.call(
                capability,
                {"title": "Cancellation contract"},
                plugin_id="test",
                cancellation=token,
                artifacts=None,
            )
        except Exception as error:
            errors.append(error)

    thread = threading.Thread(target=invoke, daemon=True)
    thread.start()
    root.after(100, adapter.drain)
    root.after(600, token.cancel)
    root.after(2200, root.quit)
    try:
        root.mainloop()
        thread.join(timeout=1)
        assert errors and errors[0].kind == "canceled"
        assert adapter._dialog_token is None
    finally:
        adapter.close()
        root.destroy()
        thread.join(timeout=1)
