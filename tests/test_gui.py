"""Real Tk shell/adapter tests. Run explicitly on a desktop-enabled build."""

import json
import sys
import time
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from pydeskui import Select, Sidebar

from pydesktools.app import IMAGE_PLUGIN, ApplicationConfig, create_application


def wait(app, predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.root.update()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("GUI did not settle")


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
        wait(app, lambda: app.task is None)
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
        app.form.set_values({"text": '{"large":"' + "世" * 30000 + '"}'})
        app.run_command("minify")
        wait(app, lambda: not app.background_busy and app.task is None)
        assert "truncated" in app.detail.text.get("1.0", "end")
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


def test_pydeskui_composition_busy_feedback_and_route_local_sidebars(tmp_path, monkeypatch):
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
        assert app.sidebar.winfo_width() == app.theme.px(188)
        assert app.header.winfo_height() == app.theme.px(64)
        assert not app.progress.winfo_ismapped()
        assert app.sidebar.home_button.instate(("selected",))
        assert not any(button.instate(("selected",)) for button in app.sidebar.buttons.values())
        normal_key = next(
            key
            for key in app.theme._image_specs
            if key.endswith(f"navigation.{id(app.sidebar.home_button):x}")
        )
        selected_key = next(
            key
            for key in app.theme._image_specs
            if key.endswith(f"navigation.{id(app.sidebar.home_button):x}.selected")
        )
        assert app.theme._image_specs[normal_key][2] is None
        assert app.theme._image_specs[selected_key][2] == app.theme.tokens["sidebar_accent"]
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

        initial_states = [button.instate(("disabled",)) for button in app.command_buttons]
        app.form.set_values({"text": '{"quick":true}'})
        app.run_command("format")
        assert not app.busy_visible
        assert [button.instate(("disabled",)) for button in app.command_buttons] == initial_states
        wait(app, lambda: app.task is None)
        assert not app.busy_visible

        app.task = SimpleNamespace(id="slow-task")
        app._schedule_busy_feedback("format")
        wait(app, lambda: app.busy_visible)
        assert app.progress.winfo_ismapped()
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
        app.root.geometry("740x600")
        app.root.update()
        assert app.workspace_shell.winfo_ismapped() == 0
        assert app.workspace.winfo_ismapped() == 0
        assert app.header.winfo_ismapped() == 0
        assert app.plugins.winfo_ismapped() == 1
        assert mapped_sidebars(app.root) == 1
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
            assert button.winfo_rooty() + button.winfo_height() <= (
                app.root.winfo_rooty() + app.root.winfo_height()
            )

        def visible_text(widget):
            result = []
            for child in widget.winfo_children():
                try:
                    result.append(str(child.cget("text")))
                except tk.TclError:
                    pass
                result.extend(visible_text(child))
            return result

        app.navigate("settings")
        app.root.update()
        assert app.plugins.winfo_ismapped() == 0
        assert app.settings.winfo_ismapped() == 1
        assert app.header.winfo_ismapped() == 0
        assert app.workspace_shell.winfo_ismapped() == 0
        assert mapped_sidebars(app.root) == 1
        assert str(app.services.store.root) in visible_text(app.settings)
        app.settings.set_mode_preference("system")
        app.change_theme()
        app._system_appearance_changed("dark")
        assert app.theme.mode == "dark"
        app.settings.set_mode_preference("light")
        app.change_theme()
        app._system_appearance_changed("dark")
        assert app.theme.mode == "light"

        app.navigate("tool", "org.pydesk.json-tools")
        app.root.update()
        assert app.workspace_shell.winfo_ismapped() == 1
        assert app.header.winfo_ismapped() == 1
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
        assert image_record["manifest"]["version"] == "0.2.0"
        assert "dialogs.choose_directory" not in image_record["manifest"]["capabilities"]
        app.navigate("tool", IMAGE_PLUGIN)
        app.run_command("import_images")
        wait(app, lambda: app.task is None and app.image_tool._photos)
        assert app.image_tool.files == [str(source)], errors
        assert len(app.result_artifacts) == 2
        assert app.image_tool._photos
        app.image_tool.variables["keep_larger"].set("1")
        wait(app, lambda: app.task is None)
        app.run_command("compress")
        wait(app, lambda: app.task is None)
        assert list(tmp_path.glob("sample-compressed*.jpg"))
        assert source.exists()
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
