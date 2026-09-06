"""Real Tk shell/adapter tests. Run explicitly on a desktop-enabled build."""

import json
import sys
import time
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydeskui import Select, Tabs

from pydesktools.app import ApplicationConfig, create_application


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
        wait(app, lambda: not app.background_busy)
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


def test_pydeskui_composition_busy_feedback_and_plugin_layout(tmp_path, monkeypatch):
    tk.NoDefaultRoot()
    monkeypatch.setattr("pydesktools.app.preferred_locale", lambda: "en")
    app = create_application(
        ApplicationConfig(data_dir=tmp_path / "profile", python=Path(sys.executable))
    )
    try:
        wait(app, lambda: not app.background_busy)
        assert isinstance(app.notebook, Tabs)
        assert isinstance(app.settings.language_select, Select)
        assert isinstance(app.settings.mode_select, Select)
        assert app.locale_preference == "system"
        assert app.theme_preference == "system"

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
        assert all(button.instate(("disabled",)) for button in app.command_buttons)
        app.task = None
        app._settle_busy_feedback()
        assert not app.busy_visible
        assert not app.command_buttons[0].instate(("disabled",))

        app.notebook.select(app.plugins)
        app.root.geometry("740x600")
        app.root.update()
        assert app.plugins.selected_id()
        visible_actions = [
            app.plugins.install_button,
            app.plugins.disable_button,
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

        assert str(app.services.store.root) not in visible_text(app.settings)
        app.settings.set_mode_preference("system")
        app.change_theme()
        app._system_appearance_changed("dark")
        assert app.theme.mode == "dark"
        app.settings.set_mode_preference("light")
        app.change_theme()
        app._system_appearance_changed("dark")
        assert app.theme.mode == "light"
    finally:
        app._close()


@pytest.mark.skipif(sys.platform != "darwin", reason="Cocoa adapter")
def test_native_panel_cancel():
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
                "dialogs.open_file",
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
