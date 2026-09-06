"""Explicit application composition and the macOS-first offline toolbox."""

import gettext
import hashlib
import json
import locale as system_locale
import queue
import sys
import threading
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from tkinter import filedialog
from typing import Protocol

from pydesktools_runtime import CloseHandle, RuntimeConfig, create_services
from pydesktools_sdk import CancellationToken
from pydeskui import (
    Dialog,
    FieldSpec,
    Frame,
    Item,
    ProgressView,
    Scheduler,
    Tabs,
    Theme,
    Toast,
    TranslationContext,
)

from .platform import PlatformAdapter
from .ui import JSONToolView, PluginManagerView, SettingsView, fields_for_schema

PLUGIN = "org.pydesk.json-tools"
LANGUAGE_PREFERENCES = ("system", "en", "zh-CN")
THEME_PREFERENCES = ("system", "light", "dark")


def preferred_locale():
    """Resolve supported UI locales without changing the process locale."""
    language = None
    if sys.platform == "darwin":
        try:
            from Foundation import NSLocale

            languages = NSLocale.preferredLanguages()
            language = str(languages[0]) if languages else None
        except (ImportError, IndexError, AttributeError):
            pass
    if not language:
        language = system_locale.getlocale()[0]
    normalized = (language or "en").replace("_", "-").lower()
    return "zh-CN" if normalized.startswith("zh") else "en"


def preferred_theme(root):
    """Resolve the current host appearance, with a safe light fallback."""
    if root.tk.call("tk", "windowingsystem") != "aqua":
        return "light"
    try:
        dark = root.tk.getboolean(root.tk.call("wm", "attributes", root._w, "-isdark"))
    except tk.TclError:
        return "light"
    return "dark" if dark else "light"


class ApplicationExtension(Protocol):
    id: str

    def register(self, services) -> CloseHandle: ...


@dataclass(frozen=True)
class ApplicationConfig:
    app_id: str = "org.pydesk.tools"
    display_name: str = "PyDeskTools"
    version: str = "0.1.0"
    data_namespace: str = "PyDeskTools"
    extensions: tuple = ()
    catalog_sources: tuple = ()
    data_dir: Path | None = None
    python: Path | None = None


class ViewRegistry:
    def __init__(self):
        self.factories = {}

    def register(self, view_id, factory):
        if view_id in self.factories:
            raise ValueError("Duplicate view ID")
        self.factories[view_id] = factory
        return CloseHandle(lambda: self.factories.pop(view_id, None))


def runtime_python(config):
    if config.python:
        return config.python
    if getattr(sys, "frozen", False):
        import shutil
        import uuid

        from platformdirs import user_data_path

        resource = Path(sys.executable).resolve().parents[1] / "Resources" / "plugin-runtime"
        manifest_bytes = (resource / "runtime.json").read_bytes()
        manifest = json.loads(manifest_bytes)
        relative = Path(manifest["executable"])
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError("Invalid runtime manifest")
        runtime_id = hashlib.sha256(manifest_bytes).hexdigest()[:20]
        data = config.data_dir or user_data_path(config.data_namespace, appauthor=False)
        destination = Path(data).resolve() / "runtimes" / runtime_id

        def verify(directory):
            for name, digest in manifest["files"].items():
                path = Path(name)
                if path.is_absolute() or ".." in path.parts:
                    raise RuntimeError("Invalid runtime inventory")
                with (directory / path).open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                        raise RuntimeError("Plugin runtime integrity check failed")

        if not destination.exists():
            verify(resource)
            destination.parent.mkdir(parents=True, exist_ok=True)
            candidate = destination.parent / (runtime_id + ".partial-" + uuid.uuid4().hex)
            try:
                shutil.copytree(resource, candidate, symlinks=True)
                verify(candidate)
                candidate.rename(destination)
            finally:
                if candidate.exists():
                    shutil.rmtree(candidate)
        verify(destination)
        return destination / relative
    return Path(sys.executable)


class Application:
    def __init__(self, config):
        if config.catalog_sources:
            raise ValueError("Online catalogs are not implemented in this release")
        self.config = config
        self.root = tk.Tk()
        self.root.title(config.display_name)
        self.root.geometry("1080x780")
        self.root.minsize(740, 600)
        self.platform = PlatformAdapter(self.root)
        self.services = create_services(
            RuntimeConfig(
                config.app_id, config.data_namespace, config.data_dir, runtime_python(config)
            ),
            platform_adapter=self.platform,
        )
        self.services.views = ViewRegistry()
        self.extension_handles = [
            extension.register(self.services) for extension in config.extensions
        ]
        self.locale_preference = self.services.store.setting("host", "locale", "system")
        if self.locale_preference not in LANGUAGE_PREFERENCES:
            self.locale_preference = "system"
        self.locale = (
            preferred_locale() if self.locale_preference == "system" else self.locale_preference
        )
        self.services.locale = self.locale
        self.services.installer.locale = self.locale
        self.theme_preference = self.services.store.setting("host", "theme", "system")
        if self.theme_preference not in THEME_PREFERENCES:
            self.theme_preference = "system"
        self.theme = Theme(
            self.root,
            mode=(
                preferred_theme(self.root)
                if self.theme_preference == "system"
                else self.theme_preference
            ),
            translator=TranslationContext(self.locale),
        )
        self.scheduler = Scheduler(self.root)
        self.toast = Toast(self.root, duration_ms=2500, theme=self.theme)
        self.events: queue.Queue = queue.Queue(maxsize=256)
        self.progress_event = None
        self.subscription = self.services.tasks.subscribe(self._event)
        self.task = None
        self.current_plugin = PLUGIN
        self.current_command = "format"
        self.json_values = None
        self.result_task = None
        self.result_artifact = None
        self.closing = False
        self.background_busy = False
        self.busy_visible = False
        self.busy_handle = None
        self.active_action = None
        self.background_token = CancellationToken()
        self.jobs = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pydesk-install")
        self._appearance_bindings = [
            (
                "<<DarkAqua>>",
                self.root.bind(
                    "<<DarkAqua>>",
                    lambda _event: self._system_appearance_changed("dark"),
                    add="+",
                ),
            ),
            (
                "<<LightAqua>>",
                self.root.bind(
                    "<<LightAqua>>",
                    lambda _event: self._system_appearance_changed("light"),
                    add="+",
                ),
            ),
        ]
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        if sys.platform == "darwin":
            self.root.tk.createcommand("::tk::mac::Quit", self.close)
        self.root.report_callback_exception = lambda kind, value, tb: self.error(str(value))
        self.scheduler.call_later(25, self._poll)
        self._provision()

    def t(self, text):
        if getattr(self, "_translation_locale", None) != self.locale:
            self._translation_locale = self.locale
            language = self.locale.replace("-", "_")
            resource = files("pydesktools").joinpath(
                "locales", language, "LC_MESSAGES", "pydesktools.mo"
            )
            self._translator = gettext.NullTranslations()
            if resource.is_file():
                with resource.open("rb") as stream:
                    self._translator = gettext.GNUTranslations(stream)
        return self._translator.gettext(text)

    def _build(self, values=None):
        self.notebook = Tabs(self.root, theme=self.theme)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=12)
        self.tools = JSONToolView(
            self.notebook,
            fields=[
                FieldSpec("text", self.t("JSON input"), "multiline", default='{"hello": "世界"}'),
                FieldSpec("indent", self.t("Indent"), "integer", default=2),
                FieldSpec("sort_keys", self.t("Sort keys"), "boolean", default=False),
            ],
            translate=self.t,
            on_search=self._search,
            on_select=self.select_command,
            on_command=self.run_command,
            theme=self.theme,
        )
        self.plugins = PluginManagerView(
            self.notebook,
            translate=self.t,
            on_install=self.install_local,
            on_restore=lambda: self._provision(restore=True),
            on_manage=self.manage,
            theme=self.theme,
            bundled_plugin_id=PLUGIN,
        )
        self.settings = SettingsView(
            self.notebook,
            translate=self.t,
            language_preference=self.locale_preference,
            mode_preference=self.theme_preference,
            on_language=self.change_language,
            on_mode=self.change_theme,
            theme=self.theme,
        )
        for name, panel in (
            ("Tools", self.tools),
            ("Plugins", self.plugins),
            ("Settings", self.settings),
        ):
            self.notebook.add(panel, text=self.t(name))
        self.tool_list = self.tools.tool_list
        self.form = self.tools.form
        self.actions = self.tools.input_actions
        self.command_buttons = self.tools.command_buttons
        self.detail = self.tools.detail
        self.plugin_list = self.plugins.plugin_list
        self.language_var = self.settings.language_var
        self.mode_var = self.settings.mode_var
        if values:
            self.form.set_values(values)
        self.progress = ProgressView(self.root, on_cancel=self.cancel, theme=self.theme)
        self.progress.pack(fill="x", padx=16, pady=(0, 8))
        self.progress.update_progress(0, self.t("Ready"))
        for identifier, factory in self.services.views.factories.items():
            extension_panel = Frame(self.notebook, theme=self.theme)
            self.notebook.add(extension_panel, text=identifier)
            factory(extension_panel)
        self.refresh()

    def _event(self, event):
        if event["type"] == "progress":
            self.progress_event = event
        else:
            self.events.put(event, timeout=5)

    def _schedule_busy_feedback(self, action=None):
        if action is not None:
            self.active_action = action
        if self.busy_visible or self.busy_handle is not None:
            return
        self.busy_handle = self.scheduler.call_later(150, self._show_busy_feedback)

    def _show_busy_feedback(self):
        self.busy_handle = None
        if self.closing or not (self.task or self.background_busy):
            return
        self.busy_visible = True
        self.progress.update_progress(0, self.t("Working…"))
        self.refresh()

    def _settle_busy_feedback(self):
        if self.task or self.background_busy:
            return
        if self.busy_handle is not None:
            self.busy_handle.cancel()
            self.busy_handle = None
        self.busy_visible = False
        self.active_action = None
        self.progress.update_progress(1, self.t("Ready"))
        self.refresh()

    def _poll(self):
        if self.closing:
            return
        self.platform.drain()
        if self.progress_event:
            event, self.progress_event = self.progress_event, None
            if self.busy_visible and self.task and event.get("task_id") == self.task.id:
                self.progress.update_progress(event.get("fraction"), event.get("message", ""))
        for _ in range(32):
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            if event["type"] == "verification":
                report = event["report"]
                expected = report.pop("clipboard_expected", None)
                if expected is not None:
                    report["clipboard_matches"] = self.root.clipboard_get() == expected
                    report["passed"] = report["passed"] and report["clipboard_matches"]
                Path(event["destination"]).write_text(json.dumps(report, indent=2) + "\n")
                self._close()
                return
            elif event["type"] == "inspect_install":
                manifest = event["manifest"]
                message = (
                    self.t("Unverified local code runs with your OS permissions. Install?")
                    + "\n\n"
                    + manifest["id"]
                    + " "
                    + manifest["version"]
                    + "\n"
                    + ", ".join(manifest["capabilities"])
                )
                path = event["path"]
                self.confirm(
                    message,
                    lambda p=path: self._background(
                        lambda: self.services.install(p, consent=True, token=self.background_token)
                    ),
                )
            elif event["type"] == "prepared":
                try:
                    self.task = self.services.commands.submit(
                        PLUGIN, event["command"], event["arguments"]
                    )
                    self.refresh()
                except Exception as error:
                    self.error(str(error))
            elif event["type"] == "background":
                self.background_busy = False
                if event.get("error"):
                    self.error(event["error"])
                self._settle_busy_feedback()
            elif self.task and event.get("task_id") == self.task.id:
                if event["type"] in ("completed", "failed"):
                    completed_action = self.active_action
                    if event["type"] == "completed":
                        result = event["result"]
                        if result["data"].get("artifact_id"):
                            if self.result_task:
                                self.services.artifacts.release("result:" + self.result_task)
                            self.result_task = self.task.id
                            self.result_artifact = result["data"]["artifact_id"]
                        view = result.get("view")
                        if view:
                            self.detail.set_content(
                                view["title"], view.get("body", ""), view.get("format", "text")
                            )
                        if completed_action == "copy":
                            self.toast.show(text=self.t("Copied to clipboard"))
                    else:
                        failure = event["error"]
                        data = failure.get("data", {})
                        suffix = (
                            f" (line {data['line']}, column {data['column']})"
                            if "line" in data
                            else ""
                        )
                        self.detail.set_content(self.t("Error"), failure["message"] + suffix)
                    self.task = None
                    self._settle_busy_feedback()
        self.scheduler.call_later(25, self._poll)

    def _background(self, callback):
        if self.background_busy or self.closing:
            return
        self.background_busy = True
        self.background_token = CancellationToken()
        self._schedule_busy_feedback()
        self.refresh()

        def work():
            error = None
            try:
                callback()
            except Exception as exc:
                error = str(exc)
            self.events.put({"type": "background", "error": error})

        self.jobs.submit(work)

    def _provision(self, restore=False):
        if not restore and self.services.store.decision(PLUGIN) is not None:
            return
        resource = files("pydesktools").joinpath("bundles", "json-tools.pdtplugin")
        if not resource.is_file():
            self.progress.update_progress(
                0, "Offline bundle missing; build the distribution first."
            )
            return

        def install():
            inventory = json.loads(
                files("pydesktools").joinpath("bundles", "inventory.json").read_text()
            )
            if (
                hashlib.sha256(resource.read_bytes()).hexdigest()
                != inventory["json-tools.pdtplugin"]
            ):
                raise ValueError("Bundled plugin integrity check failed")
            self.services.install(
                Path(str(resource)), consent=True, official=True, token=self.background_token
            )
            self.services.store.set_setting("host", "default_provisioning_completed", True)

        self._background(install)

    def refresh(self):
        records = self.services.store.all()
        self.plugins.set_records(records)
        self.plugins.set_busy(self.busy_visible)
        self._search("")
        record = self.services.store.get(self.current_plugin)
        ready = bool(record and record["enabled"])
        for index, button in enumerate(self.command_buttons):
            usable = (
                ready
                and not self.busy_visible
                and (index < 3 or self.result_artifact is not None)
            )
            button.state(["!disabled"] if usable else ["disabled"])

    def _search(self, text):
        items = []
        for record in self.services.store.all():
            if not record["enabled"]:
                continue
            for command in record["descriptor"]["commands"]:
                if record["id"] == PLUGIN and command["id"] != "format":
                    continue
                searchable = (
                    record["id"] + " " + command["id"] + " " + command["title"]
                ).casefold()
                if text.casefold() in searchable:
                    items.append(
                        Item(
                            record["id"] + ":" + command["id"],
                            command["title"],
                            record["manifest"]["name"],
                        )
                    )
        self.tool_list.set_items(items)

    def select_command(self, identifier):
        if not identifier or self.task or self.background_busy:
            return
        plugin, command = identifier.split(":", 1)
        if (plugin, command) == (self.current_plugin, self.current_command):
            return
        try:
            if self.current_plugin == PLUGIN:
                self.json_values = self.form.get_values()
            if plugin == PLUGIN:
                fields = [
                    FieldSpec("text", self.t("JSON input"), "multiline"),
                    FieldSpec("indent", self.t("Indent"), "integer", default=2),
                    FieldSpec("sort_keys", self.t("Sort keys"), "boolean", default=False),
                ]
            else:
                fields = fields_for_schema(self.services.describe(plugin, command)["input_schema"])
            values = self.json_values if plugin == PLUGIN and self.json_values else None
            self.tools.replace_form(fields, values)
            self.form = self.tools.form
            self.current_plugin, self.current_command = plugin, command
            self.tools.show_command_context(
                json_tools=plugin == PLUGIN,
                run_title=(
                    None
                    if plugin == PLUGIN
                    else self.services.describe(plugin, command)["title"]
                ),
            )
            self.result_artifact = None
            self.refresh()
        except Exception as error:
            self.error(str(error))

    def run_command(self, command):
        if self.task or self.background_busy:
            return
        try:
            if self.current_plugin != PLUGIN:
                self.task = self.services.commands.submit(
                    self.current_plugin, self.current_command, self.form.get_values()
                )
                self._schedule_busy_feedback(self.current_command)
                self.refresh()
                return
            if command in ("copy", "export"):
                arguments = {"artifact_id": self.result_artifact}
            else:
                arguments = self.form.get_values()
                if len(arguments["text"].encode()) > 32768:
                    # File creation runs off the UI thread; submit after it completes.
                    text = arguments.pop("text")

                    def prepare():
                        identifier = self.services.import_text(PLUGIN, text)
                        self.events.put(
                            {
                                "type": "prepared",
                                "command": command,
                                "arguments": {**arguments, "artifact_id": identifier},
                            }
                        )

                    self.active_action = command
                    self._background(prepare)
                    return
            self.task = self.services.commands.submit(PLUGIN, command, arguments)
            self._schedule_busy_feedback(command)
            self.refresh()
        except Exception as error:
            self._settle_busy_feedback()
            self.error(str(error))

    def cancel(self):
        self.background_token.cancel()
        if self.task:
            self.task.cancel()
            self.progress.update_progress(0, self.t("Cancel"))

    def confirm(self, message, callback):
        dialog = Dialog(
            self.root,
            title=self.config.display_name,
            message=self.t(message),
            actions=[("cancel", self.t("Cancel")), ("continue", self.t("Continue"))],
            theme=self.theme,
        )
        dialog.show(lambda result: callback() if result == "continue" else None)

    def error(self, message):
        if not self.closing:
            Dialog(
                self.root,
                title=self.t("Error"),
                message=message,
                actions=[("ok", self.t("OK"))],
                theme=self.theme,
            ).show(lambda result: None)

    def install_local(self):
        path = filedialog.askopenfilename(
            parent=self.root, filetypes=[("PyDesk plugin", "*.pdtplugin")]
        )
        if path:

            def inspect():
                from pydesktools_runtime.plugins import inspect_bundle

                manifest, _ = inspect_bundle(path)
                self.events.put({"type": "inspect_install", "manifest": manifest, "path": path})

            self._background(inspect)

    def manage(self, action):
        identifier = self.plugin_list.selected_id()
        if not identifier:
            return

        def execute():
            operation = (
                (lambda: self.services.delete_data(identifier))
                if action == "delete"
                else lambda: getattr(self.services, action)(identifier)
            )
            self._background(operation)
            if action != "enable":
                self.result_artifact = None

        if action in ("uninstall", "delete", "disable"):
            message = {
                "uninstall": "Remove plugin code? Saved data is retained.",
                "delete": "Disable this plugin and delete its saved data and settings?",
                "disable": "Active work will be canceled. Continue?",
            }[action]
            self.confirm(message, execute)
        else:
            execute()

    def change_theme(self, event=None):
        preference = self.settings.mode_preference()
        self.theme_preference = preference
        mode = preferred_theme(self.root) if preference == "system" else preference
        self.theme.configure(mode=mode)
        self.services.store.set_setting("host", "theme", preference)

    def _system_appearance_changed(self, mode):
        if self.theme_preference == "system" and self.theme.mode != mode:
            self.theme.configure(mode=mode)

    def change_language(self, event=None):
        preference = self.settings.language_preference()
        locale = preferred_locale() if preference == "system" else preference
        try:
            self.services.set_locale(locale)
        except Exception as error:
            self.settings.configure_options(self.locale_preference, self.theme_preference)
            self.error(str(error))
            return
        values = {
            field.id: (
                self.form.controls[field.id].get("1.0", "end-1c")
                if field.kind == "multiline"
                else self.form.variables[field.id].get()
            )
            for field in self.form.fields
        }
        for field in self.form.fields:
            if field.kind == "boolean":
                values[field.id] = values[field.id] == "true"
        self.locale_preference = preference
        self.locale = locale
        self.services.store.set_setting("host", "locale", preference)
        self.theme.translator.configure(locale=self.locale)
        selected = (self.current_plugin, self.current_command)
        self.current_plugin, self.current_command = PLUGIN, "format"
        self.notebook.destroy()
        self.progress.destroy()
        self._build(values if selected[0] == PLUGIN else self.json_values)
        if selected[0] != PLUGIN:
            self.select_command(":".join(selected))
            self.form.set_values(values)

    def close(self):
        if self.closing:
            return
        if self.task:
            self.confirm("Active work will be canceled. Continue?", self._close)
        else:
            self._close()

    def _close(self):
        self.closing = True
        if self.busy_handle is not None:
            self.busy_handle.cancel()
            self.busy_handle = None
        for sequence, binding in self._appearance_bindings:
            self.root.unbind(sequence, binding)
        self.subscription.close()
        self.platform.close()
        self.scheduler.close()
        for handle in reversed(self.extension_handles):
            handle.close()
        self.root.destroy()
        self.background_token.cancel()

        def finish():
            self.jobs.shutdown(wait=True, cancel_futures=True)
            self.services.close()

        threading.Thread(target=finish, daemon=False).start()

    def run(self):
        self.root.mainloop()
        return 0


def create_application(config=None):
    return Application(config or ApplicationConfig())


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Offline desktop toolbox")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument(
        "--verify-installation",
        type=Path,
        help="Run an offline diagnostic; requires a disposable --data-dir",
    )
    args = parser.parse_args()
    if args.verify_installation and not args.data_dir:
        parser.error("--verify-installation requires a disposable --data-dir")
    import time

    started = time.monotonic()
    app = create_application(ApplicationConfig(data_dir=args.data_dir))
    if args.verify_installation:
        from ._verification import start

        app.scheduler.call_later(50, lambda: start(app, args.verify_installation, started))
    return app.run()
