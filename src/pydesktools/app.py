"""Explicit application composition and the macOS-first offline toolbox."""

import gc
import gettext
import hashlib
import json
import locale as system_locale
import queue
import sys
import threading
import tkinter as tk
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from importlib.resources import files
from pathlib import Path
from tkinter import filedialog
from tkinter import font as tkfont
from typing import Any, Protocol

from pydesktools_runtime import (
    CloseHandle,
    ProfileInUseError,
    RuntimeConfig,
    create_services,
)
from pydesktools_sdk import CancellationToken
from pydeskui import (
    CommandPalette,
    Dialog,
    Frame,
    Icon,
    Item,
    Label,
    Scheduler,
    SearchEntry,
    Separator,
    Surface,
    Theme,
    Toast,
    Toolbar,
    TranslationContext,
)

from ._version import VERSION
from .platform import PlatformAdapter
from .ui import (
    GenericToolView,
    HomeView,
    ImageCompressorView,
    JSONToolView,
    PluginManagerView,
    SettingsView,
    ToolSidebar,
    _format_bytes,
    fields_for_schema,
)

PLUGIN = "org.pydesk.json-tools"
IMAGE_PLUGIN = "org.pydesk.image-compressor"
DEFAULT_PLUGINS = {
    PLUGIN: "json-tools.pdtplugin",
    IMAGE_PLUGIN: "image-compressor.pdtplugin",
}
DEFAULT_PLUGIN_VERSIONS = {PLUGIN: "0.1.1", IMAGE_PLUGIN: "0.2.2"}
LANGUAGE_PREFERENCES = ("system", "en", "zh-CN")
THEME_PREFERENCES = ("system", "light", "dark")


def application_font(root):
    """Pick the closest installed system UI family without bundling a font."""
    installed = set(tkfont.families(root))
    candidates = {
        "darwin": ("SF Pro Text", "SF Pro Display", "Helvetica Neue"),
        "win32": ("Segoe UI Variable", "Segoe UI"),
    }.get(sys.platform, ("Noto Sans CJK SC", "Noto Sans", "DejaVu Sans"))
    return next((name for name in candidates if name in installed), "TkDefaultFont")


def application_tokens(mode):
    if mode == "dark":
        return {
            "background": "#111720",
            "foreground": "#F4F7FB",
            "card": "#171F2A",
            "card_foreground": "#F4F7FB",
            "popover": "#171F2A",
            "popover_foreground": "#F4F7FB",
            "secondary": "#202B38",
            "secondary_foreground": "#F4F7FB",
            "muted": "#202B38",
            "muted_foreground": "#9BA8B8",
            "accent": "#213A5D",
            "accent_foreground": "#DCEBFF",
            "border": "#2A3442",
            "input": "#35465A",
            "sidebar": "#151D27",
            "sidebar_foreground": "#F4F7FB",
            "sidebar_accent": "#213A5D",
            "sidebar_accent_foreground": "#DCEBFF",
            "sidebar_border": "#2B394A",
            "destructive": "#E5484D",
            "primary_foreground": "#FFFFFF",
            "sidebar_primary_foreground": "#FFFFFF",
        }
    return {
        "background": "#FFFFFF",
        "foreground": "#151922",
        "card": "#FFFFFF",
        "card_foreground": "#151922",
        "popover": "#FFFFFF",
        "popover_foreground": "#151922",
        "secondary": "#F1F5FA",
        "secondary_foreground": "#151922",
        "muted": "#F1F5FA",
        "muted_foreground": "#687386",
        "accent": "#EAF3FF",
        "accent_foreground": "#1264D1",
        "border": "#E8ECF2",
        "input": "#CDD5E0",
        "sidebar": "#FFFFFF",
        "sidebar_foreground": "#151922",
        "sidebar_accent": "#EAF3FF",
        "sidebar_accent_foreground": "#1264D1",
        "sidebar_border": "#E8ECF2",
        "destructive": "#D92D20",
        "primary_foreground": "#FFFFFF",
        "sidebar_primary_foreground": "#FFFFFF",
    }


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
    _follow_system_appearance(root)
    try:
        dark = root.tk.getboolean(root.tk.call("wm", "attributes", root._w, "-isdark"))
    except tk.TclError:
        return "light"
    return "dark" if dark else "light"


def _follow_system_appearance(root):
    """Let macOS, rather than the last fixed theme, control native windows."""
    if root.tk.call("tk", "windowingsystem") != "aqua":
        return
    try:
        pending = [root]
        hosts = set()
        while pending:
            widget = pending.pop()
            hosts.add(widget.winfo_toplevel())
            pending.extend(widget.winfo_children())
        for host in hosts:
            host.wm_attributes("-appearance", "auto")
    except tk.TclError:
        pass


class ApplicationExtension(Protocol):
    id: str

    def register(self, services) -> CloseHandle: ...


@dataclass(frozen=True)
class ApplicationConfig:
    app_id: str = "org.pydesk.tools"
    display_name: str = "PyDeskTools"
    version: str = VERSION
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


def packaged_runtime_path(executable, bundle_root=None):
    executable = Path(executable).resolve()
    candidates = (
        executable.parent / "plugin-runtime",
        executable.parents[1] / "Resources" / "plugin-runtime",
        Path(bundle_root or executable.parent) / "plugin-runtime",
    )
    resource = next((candidate for candidate in candidates if candidate.is_dir()), None)
    if resource is None:
        raise RuntimeError("Packaged plugin runtime is missing")
    return resource


def runtime_python(config):
    if config.python:
        return config.python
    if getattr(sys, "frozen", False):
        import shutil
        import uuid

        from platformdirs import user_data_path

        resource = packaged_runtime_path(sys.executable, getattr(sys, "_MEIPASS", None))
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
                try:
                    candidate.rename(destination)
                except FileExistsError:
                    # Another instance atomically published the same verified runtime.
                    # Its completed directory is safe to share.
                    pass
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
        self.dnd_available = False
        self.dnd_version = None
        try:
            from tkinterdnd2 import TkinterDnD  # type: ignore[import-untyped]

            self.dnd_version = str(TkinterDnD.require(self.root))
            self.dnd_available = True
        except (ImportError, RuntimeError, tk.TclError):
            # File selection remains the fully supported fallback.
            pass
        self.root.title(config.display_name)
        logo_path = Path(__file__).parent / "assets/logo.png"
        self._application_icon = tk.PhotoImage(master=self.root, file=str(logo_path))
        self.root.iconphoto(True, self._application_icon)
        if sys.platform == "darwin":
            from AppKit import NSApplication, NSImage
            NSApplication.sharedApplication().setApplicationIconImage_(
                NSImage.alloc().initWithContentsOfFile_(str(logo_path)))
        self.root.geometry("1280x840")
        self.root.minsize(1100, 720)
        self.platform = PlatformAdapter(self.root)
        try:
            self.services = create_services(
                RuntimeConfig(
                    config.app_id, config.data_namespace, config.data_dir, config.python
                ),
                platform_adapter=self.platform,
                python_resolver=lambda: runtime_python(config),
            )
        except BaseException:
            self.root.destroy()
            raise
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
        resolved_mode = (
            preferred_theme(self.root)
            if self.theme_preference == "system"
            else self.theme_preference
        )
        self.theme = Theme(
            self.root,
            mode=resolved_mode,
            accent="#1677FF",
            tokens=application_tokens(resolved_mode),
            radius=8,
            density="comfortable",
            font_family=application_font(self.root),
            font_size=14,
            translator=TranslationContext(self.locale),
        )
        self.scheduler = Scheduler(self.root)
        self.toast = Toast(self.root, duration_ms=2500, theme=self.theme)
        self.events: queue.Queue = queue.Queue(maxsize=256)
        self.progress_event = None
        self.subscription = self.services.tasks.subscribe(self._event)
        self.task = None
        self.current_page = "home"
        self.current_plugin = PLUGIN
        self.current_command = "format"
        self.json_values = None
        self.form: Any = None
        self.generic_view = None
        self.recent_enabled = bool(self.services.store.setting("host", "recent_enabled", True))
        recent = self.services.store.setting("host", "recent_commands", [])
        self.recent_commands = recent if isinstance(recent, list) else []
        self.result_task = None
        self.result_artifact = None
        self.result_artifacts = []
        self.image_preview_pending = False
        self.preview_cache: OrderedDict = OrderedDict()
        self.preview_request_key = None
        self.deferred_image_command = None
        self.settings_origin: tuple[str, str | None] = ("home", None)
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
        if self.theme_preference == "system":
            _follow_system_appearance(self.root)
        self._key_bindings = [
            ("<Control-k>", self.root.bind("<Control-k>", self.show_command_palette, add="+")),
            ("<Command-k>", self.root.bind("<Command-k>", self.show_command_palette, add="+")),
            ("<Alt-Left>", self.root.bind("<Alt-Left>", self.go_home, add="+")),
            (
                "<Command-bracketleft>",
                self.root.bind("<Command-bracketleft>", self.go_home, add="+"),
            ),
        ]
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

    def _build(self, values=None, image_files=None):
        self.app_frame = Surface(self.root, role="background", theme=self.theme)
        self.app_frame.pack(fill="both", expand=True)

        self.workspace_shell = Surface(self.app_frame, role="background", theme=self.theme)
        self.header = Toolbar(self.workspace_shell, theme=self.theme, height=64, padding=(18, 10))
        self.header.pack(fill="x")
        self.header.pack_propagate(False)
        brand = Surface(self.header, role="background", width=212, theme=self.theme)
        brand.pack(side="left", fill="y")
        brand.pack_propagate(False)
        Icon(
            brand,
            source=Path(__file__).parent / "assets/logo-ui.svg",
            size=30,
            color=self.theme.tokens["primary"],
            theme=self.theme,
        ).pack(side="left", pady=7)
        Label(
            brand,
            text="PyDeskTools",
            variant="section",
            surface="background",
            theme=self.theme,
        ).pack(side="left", padx=(10, 0), pady=7)
        search_host = Surface(self.header, role="background", theme=self.theme)
        search_host.pack(side="left", fill="x", expand=True, padx=(16, 160))
        self.header_search = SearchEntry(
            search_host,
            on_change=self._header_changed,
            placeholder=self.t("Search tools or commands"),
            shortcut_hint="⌘ K",
            theme=self.theme,
            width=42,
        )
        self.header_search.pack(fill="x", pady=2)
        self.workspace = Surface(self.workspace_shell, role="background", theme=self.theme)
        self.workspace.pack(fill="both", expand=True)
        self.sidebar = ToolSidebar(
            self.workspace, translate=self.t, on_navigate=self.navigate, theme=self.theme
        )
        self.sidebar.pack(side="left", fill="y")
        Separator(self.workspace, orient="vertical", theme=self.theme).pack(side="left", fill="y")
        self.workspace_content = Surface(self.workspace, role="background", theme=self.theme)
        self.workspace_content.pack(side="left", fill="both", expand=True)

        self.home = HomeView(
            self.workspace_content,
            translate=self.t,
            on_search=self._home_changed,
            on_select=self.select_command,
            on_open_file=self.open_file,
            on_open_plugins=lambda: self.navigate("plugins"),
            theme=self.theme,
        )
        self.tools_host = Frame(self.workspace_content, theme=self.theme)
        self.json_tool = JSONToolView(
            self.tools_host,
            translate=self.t,
            on_command=self.run_command,
            on_reveal_export=self.reveal_in_file_manager,
            theme=self.theme,
        )
        self.image_tool = ImageCompressorView(
            self.tools_host,
            translate=self.t,
            on_command=self.run_command,
            on_preview=self.request_image_preview,
            on_discard=self.discard_image_paths,
            on_open_directory=self.open_directory,
            on_state_change=self.refresh,
            on_drop=lambda paths: self.run_command("import_images", paths),
            dnd_available=self.dnd_available,
            theme=self.theme,
        )
        if values:
            self.json_tool.form.set_values(values)
        if image_files:
            self.image_tool.set_files(image_files)

        self.plugins = PluginManagerView(
            self.app_frame,
            translate=self.t,
            on_home=lambda: self.navigate("home"),
            on_install=self.install_local,
            on_restore=lambda: self._provision(restore=True),
            on_manage=self.manage,
            theme=self.theme,
            bundled_plugin_ids=DEFAULT_PLUGINS,
            data_root=self.services.store.root,
        )
        self.settings = SettingsView(
            self.app_frame,
            translate=self.t,
            language_preference=self.locale_preference,
            mode_preference=self.theme_preference,
            recent_enabled=self.recent_enabled,
            on_home=lambda: self.navigate(*self.settings_origin),
            on_language=self.change_language,
            on_mode=self.change_theme,
            on_recent=self.change_recent,
            on_open_data=self.open_data_directory,
            on_clear_logs=self.clear_logs,
            data_path=self.services.store.root,
            version=self.config.version,
            theme=self.theme,
        )
        self.plugin_list = self.plugins.plugin_list
        self.language_var = self.settings.language_var
        self.mode_var = self.settings.mode_var
        self.form = self.json_tool.form
        self.actions = self.json_tool.input_actions
        self.command_buttons = self.json_tool.command_buttons
        self.detail: Any = self.json_tool.detail

        self.palette = CommandPalette(
            self.root,
            title=self.t("Quick search"),
            on_search=self._palette_changed,
            on_select=self.select_command,
            theme=self.theme,
        )
        self.palette_search = self.palette.search
        self.palette_results = self.palette.results
        self.palette_results.tree.configure(height=8)
        self.navigate(self.current_page, self.current_plugin)
        self.refresh()

    def navigate(self, page, plugin_id=None):
        if page == "settings" and self.current_page != "settings":
            self.settings_origin = (self.current_page, self.current_plugin)
        if page == "tool" and plugin_id:
            record = self.services.store.get(plugin_id)
            if not record or not record["enabled"]:
                page = "home"
            else:
                self.current_plugin = plugin_id
        self.current_page = page
        for panel in (self.workspace_shell, self.home, self.tools_host, self.plugins, self.settings):
            panel.pack_forget()
        if page == "home":
            self.workspace_shell.pack(fill="both", expand=True)
            self.home.pack(fill="both", expand=True)
        elif page == "tool":
            self.workspace_shell.pack(fill="both", expand=True)
            self.tools_host.pack(fill="both", expand=True)
            self._show_tool(self.current_plugin)
        elif page == "plugins":
            self.plugins.pack(fill="both", expand=True)
        else:
            self.settings.pack(fill="both", expand=True)
        self.refresh()
        if page == "tool" and self.current_plugin == IMAGE_PLUGIN and self.image_preview_pending:
            self.scheduler.call_later(0, self.request_image_preview)

    def _show_tool(self, plugin_id):
        for tool_panel in (self.json_tool, self.image_tool):
            tool_panel.pack_forget()
        if self.generic_view is not None:
            self.generic_view.destroy()
            self.generic_view = None
        record = self.services.store.get(plugin_id)
        active_panel: Frame
        if plugin_id == PLUGIN:
            active_panel = self.json_tool
            self.current_command = "format"
            self.form, self.detail = self.json_tool.form, self.json_tool.detail
        elif plugin_id == IMAGE_PLUGIN:
            active_panel = self.image_tool
            self.current_command = "import_images"
            self.detail = self.image_tool.result
        else:
            command = record["descriptor"]["commands"][0]
            self.current_command = command["id"]
            self.generic_view = GenericToolView(
                self.tools_host,
                fields=fields_for_schema(command["input_schema"]),
                title=command["title"],
                on_run=lambda: self.run_command(self.current_command),
                theme=self.theme,
            )
            active_panel = self.generic_view
            self.form, self.detail = self.generic_view.form, self.generic_view.detail
        active_panel.pack(fill="both", expand=True)

    def _home_changed(self, value):
        self._search(value, self.home.results)

    def _header_changed(self, value):
        if hasattr(self, "palette_results"):
            self._search(value, self.palette_results)

    def _palette_changed(self, value):
        self._search(value, self.palette_results)

    def go_home(self, _event=None):
        if self.current_page != "home":
            self.navigate("home")
            return "break"
        return None

    def show_command_palette(self, _event=None):
        self.palette.show()
        self.palette_search.delete(0, "end")
        self._search("", self.palette_results)
        self.palette_search.focus_set()
        return "break"

    def _palette_down(self, _event):
        children = self.palette_results.tree.get_children()
        if children:
            self.palette_results.tree.selection_set(children[0])
            self.palette_results.tree.focus(children[0])
            self.palette_results.tree.focus_set()
        return "break"

    def _palette_accept(self, _event):
        self.select_command(self.palette_results.selected_id())
        return "break"

    def _event(self, event):
        if event["type"] == "progress":
            self.progress_event = event
        else:
            self.events.put(event, timeout=5)

    def _schedule_busy_feedback(self, action=None):
        # Busy is a concurrency guard, never a global visual overlay.
        if action is not None:
            self.active_action = action
        self.busy_visible = bool(self.task or self.background_busy)

    def _settle_busy_feedback(self):
        self.busy_visible = bool(self.task or self.background_busy)
        if not self.busy_visible:
            self.active_action = None
        self.refresh()

    def _preview_key(self):
        arguments = self.image_tool.preview_arguments()
        path = Path(arguments["path"])
        stat = path.stat()
        return (str(path.resolve()), stat.st_mtime_ns, stat.st_size,
                json.dumps(arguments, sort_keys=True))

    def discard_image_paths(self, paths):
        discarded = {str(Path(path).resolve()) for path in paths}
        for key in list(self.preview_cache):
            if key[0] not in discarded:
                continue
            reference, *_ = self.preview_cache.pop(key)
            self.services.artifacts.release(reference)
        if self.preview_request_key and self.preview_request_key[0] in discarded:
            self.preview_request_key = None
        if not self.image_tool.files:
            self.image_preview_pending = False

    def _load_json_input(self, identifier, reference=None):
        path = self.services.artifacts.path(PLUGIN, identifier)
        def load():
            try:
                text = path.read_bytes().decode("utf-8")
                self.events.put({"type": "json_loaded", "text": text})
            finally:
                if reference:
                    self.services.artifacts.release(reference)
        self._background(load)

    def _clear_json_result(self):
        if self.result_task:
            self.services.artifacts.release("result:" + self.result_task)
        self.result_task = self.result_artifact = None

    def _poll(self):
        if self.closing:
            return
        self.platform.drain()
        if self.progress_event:
            event, self.progress_event = self.progress_event, None
            if self.task and event.get("task_id") == self.task.id and self.active_action == "compress":
                self.image_tool.batch_update(event.get("data", {}), event.get("fraction"))
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
            elif event["type"] == "json_loaded":
                self.json_tool.clear()
                self.json_tool.form.set_values({"text": event["text"]})
                self._clear_json_result()
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
                if self.image_preview_pending:
                    self.scheduler.call_later(0, self.request_image_preview)
            elif self.task and event.get("task_id") == self.task.id:
                if event["type"] in ("completed", "failed"):
                    completed_action = self.active_action
                    task_plugin = self.task.plugin_id
                    target_detail = self.json_tool.detail if task_plugin == PLUGIN else self.detail
                    if event["type"] == "completed":
                        result = event["result"]
                        if completed_action != "import" and result["data"].get("artifact_id"):
                            if self.result_task:
                                self.services.artifacts.release("result:" + self.result_task)
                            self.result_task = self.task.id
                            self.result_artifact = result["data"]["artifact_id"]
                        data = result["data"]
                        view = result.get("view")
                        if completed_action == "import_images" and "files" in data:
                            imported = [item["path"] for item in data["files"]]
                            combined = list(dict.fromkeys([*self.image_tool.files, *imported]))
                            if len(combined) > 1000:
                                self.error(self.t("A batch can contain at most 1000 images."))
                            else:
                                self.image_tool.set_files(combined)
                            rejected = data.get("rejected", [])
                            if rejected:
                                names = ", ".join(Path(item["path"]).name for item in rejected[:5])
                                message = self.t("Some files could not be added.") + "\n" + names
                                if len(rejected) > 5:
                                    message += f" +{len(rejected) - 5}"
                                self.error(message)
                        elif completed_action == "preview" and view:
                            self._show_image_preview(data, view, event.get("session_id"))
                        elif completed_action == "compress":
                            self.image_tool.finish_batch(data)
                        elif completed_action == "import" and data.get("artifact_id"):
                            self._load_json_input(data["artifact_id"], "result:" + self.task.id)
                        elif view and view.get("type") == "detail":
                            target_detail.set_content(
                                view["title"], view.get("body", ""), view.get("format", "text")
                            )
                            if task_plugin == PLUGIN:
                                self.json_tool.output_badge.configure(text=self.t("Formatted"))
                        if completed_action == "copy":
                            self.toast.show(text=self.t("Copied to clipboard"))
                        elif (
                            completed_action == "export"
                            and not data.get("canceled")
                            and data.get("path")
                        ):
                            self.json_tool.show_export_success(data["path"])
                            self.toast.show(
                                text=f"{self.t('Exported')}: {Path(data['path']).name}"
                            )
                        if completed_action not in ("copy", "export", "preview") and not data.get("canceled"):
                            self._remember(task_plugin, completed_action)
                    else:
                        failure = event["error"]
                        data = failure.get("data", {})
                        suffix = (
                            f" (line {data['line']}, column {data['column']})"
                            if "line" in data
                            else ""
                        )
                        if completed_action == "compress":
                            status = "canceled" if data.get("kind") in ("canceled", "forced_stop") else "failed"
                            items = [self.image_tool.file_results.get(path, {}) for path in self.image_tool.files]
                            items = [item if item.get("status") in ("completed", "skipped_larger", "failed") else
                                     {"source": path, "status": status} for path, item in zip(self.image_tool.files, items)]
                            self.image_tool.finish_batch({"items": items})
                        elif completed_action == "preview":
                            if not self.image_preview_pending:
                                self.image_tool.preview_image.configure(image="", text=self.t("Preview unavailable"))
                        elif completed_action in ("import", "copy", "export"):
                            self.error(failure["message"] + suffix)
                        else:
                            if completed_action in ("format", "minify"):
                                self._clear_json_result()
                            target_detail.set_content(self.t("Error"), failure["message"] + suffix)
                        if task_plugin == PLUGIN and completed_action in ("format", "minify"):
                            self.json_tool.output_badge.configure(text=self.t("Error"))
                    self.task = None
                    self._settle_busy_feedback()
                    if self.deferred_image_command:
                        deferred, self.deferred_image_command = self.deferred_image_command, None
                        self.scheduler.call_later(
                            0, partial(self._run_deferred_image_command, deferred)
                        )
                    elif self.image_preview_pending:
                        self.scheduler.call_later(0, self.request_image_preview)
        self.scheduler.call_later(25, self._poll)

    def _run_deferred_image_command(self, deferred):
        if self.current_page == "tool" and self.current_plugin == IMAGE_PLUGIN:
            command, paths = deferred
            self.run_command(command, paths)

    def request_image_preview(self):
        """Coalesce selection and setting changes into the latest useful preview."""
        if not self.image_tool.files or not self.image_tool.selected_path:
            self.image_preview_pending = False
            return
        self.image_preview_pending = True
        if (
            self.task
            or self.background_busy
            or self.current_page != "tool"
            or self.current_plugin != IMAGE_PLUGIN
        ):
            return
        self.image_preview_pending = False
        try:
            key = self._preview_key()
            if key in self.preview_cache:
                entry = self.preview_cache[key]
                self.preview_cache.move_to_end(key)
                self.image_tool.show_preview(*entry[1:])
                return
            self.preview_request_key = key
            self.run_command("preview")
        except (OSError, ValueError, tk.TclError):
            self.image_tool.preview_image.configure(image="", text=self.t("Preview unavailable"))

    def _show_image_preview(self, data, view, session=None):
        identifiers = [data["before_artifact_id"], data["after_artifact_id"]]
        try:
            current_key = self._preview_key()
        except (OSError, ValueError, tk.TclError):
            current_key = None
        key = self.preview_request_key
        if key != current_key:
            if session:
                for identifier in identifiers:
                    self.services.artifacts.release(session, identifier)
            return
        reference = "image-preview:" + identifiers[0]
        paths = []
        for identifier in identifiers:
            self.services.artifacts.acquire(IMAGE_PLUGIN, identifier, reference)
            paths.append(self.services.artifacts.path(IMAGE_PLUGIN, identifier))
            if session:
                self.services.artifacts.release(session, identifier)
        metadata = view.get("metadata", {})
        summary = self.t("Original") + f": {_format_bytes(metadata.get('original_bytes', 0))} · "
        summary += self.t("Estimated") + f": {_format_bytes(metadata.get('estimated_bytes', 0))}\n"
        summary += f"{metadata.get('width', 0)} × {metadata.get('height', 0)} px"
        previous = self.preview_cache.pop(key, None)
        if previous:
            self.services.artifacts.release(previous[0])
        self.preview_cache[key] = (reference, paths[0], paths[1], summary)
        while len(self.preview_cache) > 12:
            _, entry = self.preview_cache.popitem(last=False)
            self.services.artifacts.release(entry[0])
        self.image_tool.show_preview(paths[0], paths[1], summary)

    def _remember(self, plugin_id, command_id):
        import time

        entry = {"plugin_id": plugin_id, "command_id": command_id, "time": int(time.time())}
        self.recent_commands = [
            item
            for item in self.recent_commands
            if (item.get("plugin_id"), item.get("command_id")) != (plugin_id, command_id)
        ]
        self.recent_commands.insert(0, entry)
        self.recent_commands = self.recent_commands[:10]
        self.services.store.set_setting("host", "recent_commands", self.recent_commands)

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
                self.services.logger.exception("Background operation failed")
                error = str(exc)
            self.events.put({"type": "background", "error": error})

        self.jobs.submit(work)

    def _provision(self, restore=False):
        pending = []
        bundle_root = files("pydesktools").joinpath("bundles")
        for identifier, filename in DEFAULT_PLUGINS.items():
            decision = self.services.store.decision(identifier)
            record = self.services.store.get(identifier)
            if restore and record:
                continue
            needs_update = bool(
                record
                and decision in ("enabled", "disabled")
                and record["manifest"]["version"] != DEFAULT_PLUGIN_VERSIONS[identifier]
            )
            if restore or decision is None or needs_update:
                resource = bundle_root.joinpath(filename)
                if resource.is_file():
                    pending.append(
                        (
                            "update" if needs_update else "install",
                            identifier,
                            filename,
                            resource,
                            decision,
                        )
                    )
        if not pending:
            return

        def install():
            import time

            inventory = json.loads(bundle_root.joinpath("inventory.json").read_text())
            for operation, identifier, filename, resource, previous_decision in pending:
                assert resource is not None
                if hashlib.sha256(resource.read_bytes()).hexdigest() != inventory[filename]:
                    raise ValueError("Bundled plugin integrity check failed")
                if operation == "update":
                    self.services.uninstall(identifier)
                for attempt in range(2):
                    try:
                        self.services.install(
                            Path(str(resource)),
                            consent=True,
                            official=True,
                            token=self.background_token,
                            progress=lambda phase, plugin=identifier: self.services.logger.info(
                                "Provisioning %s: %s", plugin, phase
                            ),
                        )
                        break
                    except Exception as exc:
                        if attempt:
                            raise RuntimeError(f"{identifier}: {exc}") from exc
                        time.sleep(0.1)
                if operation == "update" and previous_decision == "disabled":
                    self.services.disable(identifier)
            self.services.store.set_setting("host", "default_provisioning_completed", True)

        self._background(install)

    def refresh(self):
        records = self.services.store.all()
        enabled = [record for record in records if record["enabled"]]
        self.plugins.set_records(records)
        self.plugins.set_running(self.services._workers)
        self.busy_visible = bool(self.task or self.background_busy)
        self.plugins.set_busy(self.busy_visible)
        self.sidebar.set_records(
            enabled,
            current_plugin=self.current_plugin,
            page=self.current_page,
        )
        self._search(self.home.search.get(), self.home.results)
        self._refresh_recent(enabled)
        record = self.services.store.get(self.current_plugin)
        ready = bool(record and record["enabled"])
        if self.current_page == "tool" and not ready:
            self.cancel()
            self.navigate("home")
            return
        for name, button in self.json_tool.buttons.items():
            usable = ready and not self.busy_visible
            if name in ("copy", "export", "swap"):
                usable = usable and self.result_artifact is not None
            button.state(["!disabled"] if usable else ["disabled"])
        for name, button in self.image_tool.buttons.items():
            usable = ready and (not self.busy_visible or self.active_action == "preview")
            if name == "compress":
                usable = usable and bool(self.image_tool.pending_paths())
                button.configure(text=self.image_tool.compression_label())
            button.state(["!disabled"] if usable else ["disabled"])

        self.image_tool.set_busy(self.active_action == "compress")

    @staticmethod
    def _normalized(value):
        return " ".join(value.casefold().replace("_", " ").replace("-", " ").split())

    def _command_title(self, plugin, command):
        titles = {
            PLUGIN: {"format": "Format JSON", "minify": "Minify JSON", "import": "Import JSON",
                     "copy": "Copy result", "export": "Export JSON"},
            IMAGE_PLUGIN: {"import_images": "Add images", "preview": "Compression preview",
                           "compress": "Compress images"},
        }
        return self.t(titles.get(plugin, {}).get(command["id"], command["title"]))

    def _search(self, text, target):
        query = self._normalized(text)
        scored = []
        recent_order = {
            f"{entry.get('plugin_id')}:{entry.get('command_id')}": index
            for index, entry in enumerate(self.recent_commands)
        }
        for record in self.services.store.all():
            if not record["enabled"]:
                continue
            plugin_text = self._normalized(record["id"] + " " + record["manifest"]["name"])
            for command in record["descriptor"]["commands"]:
                identifier = record["id"] + ":" + command["id"]
                if not query and identifier not in recent_order:
                    continue
                command_text = self._normalized(
                    command["id"] + " " + command["title"] + " " + command.get("description", "")
                )
                haystack = plugin_text + " " + command_text
                tokens = query.split()
                if query and not all(token in haystack for token in tokens):
                    continue
                score = sum(
                    3
                    if command_text.startswith(token)
                    else 2
                    if plugin_text.startswith(token)
                    else 1
                    for token in tokens
                )
                scored.append(
                    (
                        score,
                        Item(
                            identifier,
                            self._command_title(record["id"], command),
                            record["manifest"]["name"],
                        ),
                    )
                )
        if not query:
            scored.sort(key=lambda pair: recent_order[pair[1].id])
        else:
            scored.sort(key=lambda pair: (-pair[0], pair[1].title.casefold()))
        target.set_items([item for _score, item in scored[:20]])

    def _refresh_recent(self, enabled):
        enabled_ids = {record["id"] for record in enabled}
        valid = []
        items = []
        for entry in self.recent_commands:
            if entry.get("plugin_id") not in enabled_ids:
                continue
            record = self.services.store.get(entry["plugin_id"])
            command = next(
                (
                    item
                    for item in record["descriptor"]["commands"]
                    if item["id"] == entry.get("command_id")
                ),
                None,
            )
            if command:
                valid.append(entry)
                items.append(
                    Item(
                        entry["plugin_id"] + ":" + entry["command_id"],
                        self._command_title(record["id"], command),
                        record["manifest"]["name"],
                    )
                )
        if valid != self.recent_commands:
            self.recent_commands = valid[:10]
            self.services.store.set_setting("host", "recent_commands", self.recent_commands)
        self.home.set_recent(items[:10] if self.recent_enabled else [])

    def select_command(self, identifier):
        if not identifier or self.task or self.background_busy:
            return
        plugin, command = identifier.split(":", 1)
        try:
            self.navigate("tool", plugin)
            self.current_command = command
            self.palette.hide()
            if plugin == PLUGIN:
                self.json_tool.editor.focus_set()
            elif plugin == IMAGE_PLUGIN and command == "import_images":
                self.run_command(command)
        except Exception as error:
            self.error(str(error))

    def run_command(self, command, image_paths: list[str] | tuple[str, ...] | None = None):
        if self.task and self.active_action == "preview" and self.current_plugin == IMAGE_PLUGIN and command != "preview":
            self.deferred_image_command = (command, image_paths)
            return True
        if self.task or self.background_busy:
            return False
        try:
            arguments: dict[str, Any]
            if self.current_plugin == IMAGE_PLUGIN:
                if command == "import_images":
                    arguments = {"paths": list(image_paths)} if image_paths is not None else {}
                elif command == "preview":
                    arguments = self.image_tool.preview_arguments()
                    arguments = {
                        key: value for key, value in arguments.items() if value is not None
                    }
                else:
                    arguments = self.image_tool.arguments()
                    arguments = {
                        key: value for key, value in arguments.items() if value is not None
                    }
                    if command == "compress" and not arguments.get("paths"):
                        self.refresh()
                        return False
                self.task = self.services.commands.submit(IMAGE_PLUGIN, command, arguments)
                if command == "compress":
                    self.image_tool.begin_batch(arguments["paths"], self.cancel)
                self._schedule_busy_feedback(command)
                self.refresh()
                return True
            if self.current_plugin != PLUGIN:
                self.task = self.services.commands.submit(
                    self.current_plugin, self.current_command, self.form.get_values()
                )
                self._schedule_busy_feedback(self.current_command)
                self.refresh()
                return
            if command == "swap":
                if self.result_artifact:
                    self._load_json_input(self.result_artifact)
                return
            if command == "clear":
                self.json_tool.clear()
                self._clear_json_result()
                self.refresh()
                return
            if command in ("format", "minify", "import", "export"):
                self.json_tool.clear_export_feedback()
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
            if self.active_action == "compress":
                self.image_tool.batch_progress.update_progress(None, self.t("Cancel"))

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

    def open_file(self):
        paths = filedialog.askopenfilenames(
            parent=self.root,
            filetypes=[
                (self.t("Supported files"), "*.json *.jpg *.jpeg *.png *.webp"),
                (self.t("All files"), "*"),
            ],
        )
        if not paths:
            return
        selected = [Path(path) for path in paths]
        suffixes = {path.suffix.casefold() for path in selected}
        if suffixes <= {".jpg", ".jpeg", ".png", ".webp"}:
            record = self.services.store.get(IMAGE_PLUGIN)
            if not record or not record["enabled"]:
                self.error(self.t("Enable Image Compressor to open image files."))
                return
            self.navigate("tool", IMAGE_PLUGIN)
            self.run_command("import_images", [str(path) for path in selected])
        elif len(selected) == 1 and selected[0].suffix.casefold() == ".json":
            record = self.services.store.get(PLUGIN)
            if not record or not record["enabled"]:
                self.error(self.t("Enable JSON Tools to open JSON files."))
                return
            try:
                text = selected[0].read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                self.error(str(exc))
                return
            self.json_tool.form.set_values({"text": text})
            self.navigate("tool", PLUGIN)
        else:
            self.error(self.t("No enabled tool supports this file type."))

    def change_recent(self):
        self.recent_enabled = self.settings.recent_var.get() == "1"
        self.services.store.set_setting("host", "recent_enabled", self.recent_enabled)
        self.refresh()

    def open_data_directory(self):
        self.open_directory(self.services.store.root)

    def open_directory(self, path):
        import subprocess

        target = str(Path(path))
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", target])
            elif sys.platform == "win32":
                subprocess.Popen(["explorer.exe", target])
            else:
                subprocess.Popen(["xdg-open", target])
        except OSError as exc:
            self.error(str(exc))

    def reveal_in_file_manager(self, path):
        import subprocess

        target = Path(path)
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(target)])
            elif sys.platform == "win32":
                subprocess.Popen(["explorer.exe", "/select,", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target.parent)])
        except OSError as exc:
            self.error(str(exc))

    def clear_logs(self):
        logs = self.services.store.root / "logs"
        removed = 0
        for path in logs.glob("diagnostics.log.*"):
            if path.is_file():
                path.unlink()
                removed += 1
        self.toast.show(text=self.t("Old logs cleared") + f" ({removed})")

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
        self.theme.configure(mode=mode, tokens=application_tokens(mode), accent="#1677FF")
        if preference == "system":
            _follow_system_appearance(self.root)
        self.services.store.set_setting("host", "theme", preference)

    def _system_appearance_changed(self, mode):
        if self.theme_preference == "system":
            if self.theme.mode != mode:
                self.theme.configure(mode=mode, tokens=application_tokens(mode), accent="#1677FF")
            _follow_system_appearance(self.root)

    def change_language(self, event=None):
        preference = self.settings.language_preference()
        locale = preferred_locale() if preference == "system" else preference
        try:
            self.services.set_locale(locale)
        except Exception as error:
            self.settings.configure_options(self.locale_preference, self.theme_preference)
            self.error(str(error))
            return
        values = self.json_tool.form.get_values()
        image_files = list(self.image_tool.files)
        selected_page = self.current_page
        selected_plugin = self.current_plugin
        self.locale_preference = preference
        self.locale = locale
        self.services.store.set_setting("host", "locale", preference)
        self.theme.translator.configure(locale=self.locale)
        self.palette.destroy()
        self.app_frame.destroy()
        self._build(values, image_files)
        self.navigate(selected_page, selected_plugin)
        # Finalize destroyed Tk variables on their owning thread after a rebuild.
        gc.collect()

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
        for sequence, binding in self._key_bindings:
            self.root.unbind(sequence, binding)
        self.subscription.close()
        for entry in self.preview_cache.values():
            self.services.artifacts.release(entry[0])
        self.preview_cache.clear()
        self.platform.close()
        self.scheduler.close()
        for handle in reversed(self.extension_handles):
            handle.close()
        self.root.destroy()
        self.background_token.cancel()

        def finish(jobs=self.jobs, services=self.services):
            jobs.shutdown(wait=True, cancel_futures=True)
            services.close()

        self._shutdown_thread = threading.Thread(target=finish, daemon=False)
        self._shutdown_thread.start()

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
    if args.verify_installation:
        args.verify_installation.write_text(
            json.dumps({"passed": False, "stage": "launching_application"}, indent=2) + "\n"
        )
    import time

    started = time.monotonic()
    try:
        app = create_application(ApplicationConfig(data_dir=args.data_dir))
    except ProfileInUseError:
        # A second desktop launch should defer to the instance that owns the profile,
        # not surface PyInstaller's unhandled-exception dialog.
        return 0
    if args.verify_installation:
        from ._verification import start

        app.scheduler.call_later(50, lambda: start(app, args.verify_installation, started))
    return app.run()
