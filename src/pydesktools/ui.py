"""Application-owned views composed exclusively from PyDeskUI primitives."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageTk
from pydeskui import (
    Alert,
    Badge,
    Button,
    Card,
    CodeEditor,
    DetailView,
    Entry,
    FieldSpec,
    Form,
    Frame,
    Icon,
    Item,
    ItemList,
    Label,
    NavigationItem,
    Popover,
    ProgressView,
    ScrollArea,
    SearchEntry,
    SegmentedControl,
    Select,
    Separator,
    Sidebar,
    Spinbox,
    SplitPane,
    Surface,
    Switch,
    Toolbar,
    Tooltip,
)

JSON_PLUGIN = "org.pydesk.json-tools"
IMAGE_PLUGIN = "org.pydesk.image-compressor"


class PaddedSurface(Surface):
    """Apply layout padding to the frame, including on Tk's Aqua backend."""

    def __init__(self, master, *, padding=0, **options):
        super().__init__(master, padding=padding, **options)
        self.configure(padding=padding)


class ContentCard(Card):
    """Application surfaces use spacing; opt into a boundary only when needed."""

    def __init__(self, master, *, theme, **options):
        options.setdefault("bordered", False)
        super().__init__(master, theme=theme, **options)


class HeroSearch(SearchEntry):
    """Roomier home search, retaining PyDeskUI's focus and debounce behavior."""

    def __init__(self, master, **options):
        options.setdefault("content_padding", (14, 20))
        super().__init__(master, **options)


def _format_bytes(value):
    """Format byte counts with binary thresholds and familiar UI units."""
    size = max(0, int(value or 0))
    if size < 1024:
        return f"{size:,} B"
    if size < 1024 * 1024:
        return f"{size / 1024:,.1f} KB"
    return f"{size / (1024 * 1024):,.1f} MB"


def _page_header(master, *, title, subtitle, icon, theme):
    """Create the shared title treatment used by every workspace page."""
    header = PaddedSurface(master, role="background", theme=theme)
    Icon(
        header,
        name=icon,
        size=24,
        color=theme.tokens["primary"],

        theme=theme,
    ).pack(side="left", padx=(0, 14))
    copy = PaddedSurface(header, role="background", theme=theme)
    copy.pack(side="left", fill="x", expand=True)
    Label(copy, text=title, variant="title", surface="background", theme=theme).pack(anchor="w")
    Label(
        copy,
        text=subtitle,
        variant="muted",
        surface="background",
        theme=theme,
    ).pack(anchor="w", pady=(5, 0))
    return header


def _section_heading(master, *, title, subtitle=None, theme):
    box = PaddedSurface(master, role="card", theme=theme)
    Label(box, text=title, variant="section", theme=theme).pack(anchor="w")
    if subtitle:
        Label(box, text=subtitle, variant="muted", theme=theme).pack(anchor="w", pady=(4, 0))
    return box


def _settings_row(master, *, title, description, icon, theme):
    row = PaddedSurface(master, role="card", theme=theme)
    Icon(row, name=icon, size=21, color=theme.tokens["muted_foreground"], theme=theme).pack(
        side="left", padx=(2, 16), pady=16
    )
    copy = PaddedSurface(row, role="card", theme=theme)
    copy.pack(side="left", fill="x", expand=True, pady=16)
    Label(copy, text=title, theme=theme).pack(anchor="w")
    Label(copy, text=description, variant="muted", wraplength=260, theme=theme).pack(
        anchor="w", pady=(6, 0)
    )
    return row


def fields_for_schema(schema):
    """Map an application command schema to PyDeskUI's generic form model."""
    if schema.get("type") != "object":
        raise ValueError("Command forms require an object input schema")
    fields = []
    for identifier, spec in schema.get("properties", {}).items():
        field_kind: Literal["text", "multiline", "integer", "boolean", "choice"]
        kind = spec.get("type")
        choices = tuple(spec.get("enum", ()))
        if choices and all(isinstance(value, str) for value in choices):
            field_kind = "choice"
        elif kind == "boolean":
            field_kind = "boolean"
        elif kind == "integer":
            field_kind = "integer"
        elif kind == "string":
            field_kind = "text"
        else:
            raise ValueError(f"Field {identifier}: this schema needs a custom application view")
        fields.append(
            FieldSpec(
                identifier,
                spec.get("title", identifier),
                field_kind,
                identifier in schema.get("required", ()),
                spec.get("default"),
                choices,
            )
        )
    return fields


class ToolSidebar(Sidebar):
    """Persistent application navigation shared by every route."""

    def __init__(self, master, *, translate, on_navigate, theme):
        # Match the PyDeskUI gallery rail: compact, quiet, and separated from
        # the workspace by the shell's single vertical divider.
        super().__init__(master, theme=theme, width=232, padding=(12, 22))
        self.pack_propagate(False)
        self.t = translate
        self.on_navigate = on_navigate
        self.records = {}
        self.buttons = {}
        self._order = ()
        self.home_button = NavigationItem(
            self,
            text=self.t("Home"),
            command=lambda: on_navigate("home", None),
            theme=theme,
            selected=False,
            icon="home",
        )
        self.home_button.pack(fill="x", pady=(0, 24))
        Label(
            self,
            text=self.t("Enabled tools"),
            variant="muted",
            surface="sidebar",
            theme=theme,
        ).pack(anchor="w", pady=(0, 8), padx=6)
        self.tools_host = PaddedSurface(self, role="sidebar", theme=theme)
        self.tools_host.pack(fill="x")
        PaddedSurface(self, role="sidebar", theme=theme).pack(fill="both", expand=True)
        Separator(self, theme=theme).pack(fill="x", pady=(16, 12))
        self.plugins_button = NavigationItem(
            self,
            text=self.t("Plugin center"),
            command=lambda: on_navigate("plugins", None),
            theme=theme,
            icon="plugin",
        )
        self.plugins_button.pack(fill="x", pady=(0, 6))
        self.settings_button = NavigationItem(
            self,
            text=self.t("Settings"),
            command=lambda: on_navigate("settings", None),
            theme=theme,
            icon="settings",
        )
        self.settings_button.pack(fill="x")
        status = PaddedSurface(self, role="sidebar", theme=theme)
        status.pack(fill="x", padx=6, pady=(22, 0))
        Icon(status, name="check", size=14, color="#36A64F", theme=theme).pack(side="left")
        Label(
            status,
            text=self.t("Local mode (offline)"),
            variant="muted",
            surface="sidebar",
            theme=theme,
        ).pack(side="left", padx=(8, 0))

    def set_records(self, records, *, current_plugin=None, page="home"):
        records = tuple(records)
        self.records = {record["id"]: record for record in records}
        order = tuple(record["id"] for record in records)
        for identifier in set(self.buttons) - set(order):
            self.buttons.pop(identifier).destroy()
        for record in records:
            identifier = record["id"]
            display_name = self.t(record["manifest"]["name"])
            button = self.buttons.get(identifier)
            if button is None:
                button = NavigationItem(
                    self.tools_host,
                    text=display_name,
                    command=lambda value=identifier: self.on_navigate("tool", value),
                    theme=self.theme,
                    icon="json" if identifier == JSON_PLUGIN else "image",
                )
                self.buttons[identifier] = button
            elif button.cget("text") != display_name:
                button.configure(text=display_name)
            button.configure(selected=identifier == current_plugin and page == "tool")
        if order != self._order:
            for identifier in order:
                self.buttons[identifier].pack_forget()
                self.buttons[identifier].pack(fill="x", pady=3)
            self._order = order
        self.home_button.configure(selected=page == "home")
        self.plugins_button.configure(selected=page == "plugins")
        self.settings_button.configure(selected=page == "settings")


class HomeView(PaddedSurface):
    """Search-first home page with bounded sections and useful empty states."""

    def __init__(
        self, master, *, translate, on_search, on_select, on_open_file, on_open_plugins, theme
    ):
        super().__init__(master, theme=theme)
        self.t = translate
        viewport = ScrollArea(self, bordered=False, theme=theme, resize_debounce_ms=60)
        viewport.pack(fill="both", expand=True)
        body = viewport.content
        body.configure(padding=(42, 54, 42, 36))

        self.hero = PaddedSurface(body, role="background", theme=theme)
        self.hero.pack(fill="x")
        hero_title = PaddedSurface(self.hero, role="background", theme=theme)
        hero_title.pack()
        Icon(
            hero_title,
            name="plus",
            size=28,
            color=theme.tokens["primary"],

            theme=theme,
        ).pack(side="left", padx=(0, 14))
        Label(
            hero_title,
            text=self.t("Welcome to PyDeskTools"),
            variant="display",
            surface="background",
            theme=theme,
        ).pack(side="left")
        Label(
            self.hero,
            text=self.t("Find tools and commands quickly, and process data and files efficiently."),
            variant="muted",
            surface="background",
            theme=theme,
        ).pack(anchor="center", pady=(10, 30))
        self.search_card = PaddedSurface(self.hero, role="background", theme=theme)
        self.search_card.pack(fill="x", padx=24)
        self.search = HeroSearch(
            self.search_card,
            on_change=on_search,
            placeholder=self.t("Search tools or commands, e.g. format JSON, compress images…"),
            shortcut_hint="⌘ K",
            theme=theme,
        )
        self.search.pack(fill="x")
        self.results = ItemList(self.search_card, theme=theme, on_select=on_select)
        self.results.tree.configure(height=4)

        shortcuts = PaddedSurface(self.hero, role="background", theme=theme)
        shortcuts.pack(pady=(18, 0))
        for text, icon, command in (
            ("Search tools", "search", self.search.focus_set),
            ("Find commands", "check", self.search.focus_set),
            ("Open file", "upload", on_open_file),
        ):
            Button(
                shortcuts,
                text=self.t(text),
                icon=icon,
                command=command,
                variant="ghost",
                theme=theme,
            ).pack(side="left", padx=18)

        recent_card = PaddedSurface(body, role="background", padding=4, theme=theme)
        recent_card.pack(fill="x", pady=(38, 0))
        recent_header = PaddedSurface(recent_card, role="background", theme=theme)
        recent_header.pack(fill="x")
        Icon(
            recent_header,
            name="download",
            size=19,
            color=theme.tokens["muted_foreground"],

            theme=theme,
        ).pack(side="left", padx=(0, 10))
        Label(recent_header, text=self.t("Continue working"), variant="section", theme=theme).pack(
            side="left"
        )
        self.recent = ItemList(recent_card, theme=theme, on_select=on_select)
        self.recent.tree.configure(height=2)
        self.recent_empty = Label(
            recent_card,
            text=self.t("Your recent local work will appear here."),
            variant="muted",
            theme=theme,
        )

        guide = ContentCard(body, theme=theme, padding=24)
        guide.pack(fill="x", pady=(22, 0))
        guide_title = PaddedSurface(guide, role="card", theme=theme)
        guide_title.pack(fill="x")
        Icon(
            guide_title,
            name="plus",
            size=19,
            color=theme.tokens["primary"],

            theme=theme,
        ).pack(side="left", padx=(0, 10))
        Label(
            guide_title,
            text=self.t("Two ways to get started"),
            variant="section",
            surface="card",
            theme=theme,
        ).pack(side="left")
        columns = PaddedSurface(guide, role="card", theme=theme)
        columns.pack(fill="x", pady=(26, 24))
        columns.columnconfigure((0, 2), weight=1, uniform="guide")
        for column, (title, description, icon) in enumerate(
            (
                (
                    self.t("Choose a tool from the sidebar"),
                    self.t("Select an enabled tool and start working with local data."),
                    "plugin",
                ),
                (
                    self.t("Drop or open a supported file"),
                    self.t("Supported files are routed directly to the right local tool."),
                    "upload",
                ),
            )
        ):
            target = column * 2
            card = PaddedSurface(columns, role="card", padding=(4, 10), theme=theme)
            card.grid(row=0, column=target, sticky="nsew")
            Icon(
                card,
                name=icon,
                size=25,
                color=theme.tokens["primary"],

                theme=theme,
            ).pack(side="left", padx=(0, 16))
            copy = PaddedSurface(card, role="card", theme=theme)
            copy.pack(side="left", fill="x", expand=True)
            Label(copy, text=title, variant="section", surface="card", theme=theme).pack(anchor="w")
            Label(
                copy,
                text=description,
                variant="muted",
                surface="card",
                wraplength=330,
                theme=theme,
            ).pack(anchor="w", pady=(6, 0))
        actions = PaddedSurface(guide, role="card", theme=theme)
        actions.pack(fill="x")
        Button(
            actions,
            text=self.t("Open file"),
            command=on_open_file,
            theme=theme,
            variant="primary",
            icon="upload",
        ).pack(side="left")
        Button(
            actions,
            text=self.t("Manage plugins"),
            command=on_open_plugins,
            theme=theme,
            variant="link",
            icon="plugin",
        ).pack(side="right")

    def set_results(self, items):
        items = tuple(items)
        self.results.set_items(items)
        if self.search.get().strip() and items:
            self.results.pack(fill="x", pady=(8, 0))
        else:
            self.results.pack_forget()

    def set_recent(self, items):
        items = tuple(items)[:2]
        self.recent.set_items(items)
        if items:
            self.recent_empty.pack_forget()
            self.recent.pack(fill="x", pady=(14, 0))
        else:
            self.recent.pack_forget()
            self.recent_empty.pack(anchor="w", pady=(12, 2))


class _JSONValues:
    def __init__(self, editor, indent, sort_keys):
        self.editor, self.indent, self.sort_keys = editor, indent, sort_keys

    def get_values(self):
        return {
            "text": self.editor.get("1.0", "end-1c"),
            "indent": int(self.indent.get() or 2),
            "sort_keys": self.sort_keys.get() == "1",
        }

    def set_values(self, values):
        if "text" in values:
            self.editor.delete("1.0", "end")
            self.editor.insert("1.0", values["text"])
        if "indent" in values:
            self.indent.set(str(values["indent"]))
        if "sort_keys" in values:
            self.sort_keys.set("1" if values["sort_keys"] else "0")


class _JSONOutput(CodeEditor):
    """Read-only code surface that retains DetailView's small host contract."""

    def set_content(self, _title, body, _format=None):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", body)
        self.text.configure(state="disabled")
        self._update_chrome()


class JSONToolView(PaddedSurface):
    """Aligned input/output workbench with one functional center divider."""

    def __init__(self, master, *, translate, on_command, on_reveal_export, theme):
        super().__init__(master, theme=theme)
        self.t = translate
        self.on_reveal_export = on_reveal_export
        self.export_path: Path | None = None
        self.indent_var = tk.StringVar(master=self, value="2")
        self.sort_var = tk.StringVar(master=self, value="0")
        title_surface = _page_header(
            self,
            title=self.t("JSON Formatter"),
            subtitle=self.t("All processing happens locally. Your data never leaves this device."),
            icon="json",
            theme=theme,
        )
        title_surface.pack(fill="x", padx=28, pady=(24, 18))
        toolbar = Toolbar(self, theme=theme, padding=(0, 16))
        toolbar.pack(fill="x", padx=28)
        self.input_actions = toolbar
        self.buttons = {}
        for title, command, variant, icon in (
            ("Format", "format", "primary", "check"),
            ("Minify", "minify", "secondary", "minus"),
            ("Import", "import", "default", "upload"),
            ("Clear", "clear", "default", "trash"),
        ):
            button = Button(
                toolbar,
                text=self.t(title),
                command=lambda value=command: on_command(value),
                theme=theme,
                variant=variant,
                icon=icon,
            )
            button.pack(side="left", padx=(0, 6))
            self.buttons[command] = button
        for title, command, icon in (
            ("Export", "export", "download"),
            ("Copy", "copy", "copy"),
        ):
            button = Button(
                toolbar,
                text=self.t(title),
                command=lambda value=command: on_command(value),
                theme=theme,
                variant="secondary" if command == "copy" else "default",
                icon=icon,
            )
            button.pack(side="right", padx=(6, 0))
            self.buttons[command] = button
        self.settings_button = Button(
            toolbar,
            text=self.t("Options"),
            command=self._show_options,
            theme=theme,
        )
        self.settings_button.pack(side="right", padx=(6, 0))
        self.options = Popover(
            self.settings_button,
            close_on_return=True,
            theme=theme,
        )
        Label(self.options.content, text=self.t("Indent"), theme=theme).pack(anchor="w")
        self.indent_control = Spinbox(
            self.options.content,
            textvariable=self.indent_var,
            from_=0,
            to=8,
            width=8,
            theme=theme,
        )
        self.indent_control.pack(anchor="w", pady=(4, 10))
        Switch(
            self.options.content,
            text=self.t("Sort keys"),
            variable=self.sort_var,
            onvalue="1",
            offvalue="0",
            theme=theme,
        ).pack(anchor="w")
        Button(
            self.options.content,
            text=self.t("Done"),
            command=self.options.hide,
            variant="primary",
            size="small",
            theme=theme,
        ).pack(anchor="e", pady=(14, 0))
        self.split = SplitPane(self, orient="horizontal", theme=theme)
        self.split.pack(fill="both", expand=True, padx=28, pady=(0, 24))
        input_card = ContentCard(self.split, padding=1, theme=theme)
        input_header = PaddedSurface(input_card, role="card", padding=(16, 14), theme=theme)
        input_header.pack(fill="x")
        Label(input_header, text=self.t("Input (raw JSON)"), variant="section", theme=theme).pack(
            side="left"
        )
        self.input_count = Badge(input_header, text="0", variant="secondary", theme=theme)
        self.input_count.pack(side="right")
        editor_host = PaddedSurface(input_card, role="card", padding=(16, 12), theme=theme)
        editor_host.pack(fill="both", expand=True)
        self.editor = CodeEditor(editor_host, bordered=False, theme=theme)
        self.editor.pack(fill="both", expand=True)
        self.editor.insert("1.0", '{"hello": "世界"}')
        self.editor.text.bind("<<Modified>>", self._update_input_count, add="+")
        output_card = ContentCard(self.split, padding=1, theme=theme)
        output_header = PaddedSurface(output_card, role="card", padding=(16, 14), theme=theme)
        output_header.pack(fill="x")
        Label(
            output_header, text=self.t("Output (formatted result)"), variant="section", theme=theme
        ).pack(side="left")
        self.output_badge = Badge(
            output_header, text=self.t("Waiting"), variant="secondary", theme=theme
        )
        self.output_badge.pack(side="right")
        detail_host = PaddedSurface(output_card, role="card", padding=(16, 12), theme=theme)
        detail_host.pack(fill="both", expand=True)
        self.detail = _JSONOutput(detail_host, readonly=True, bordered=False, theme=theme)
        self.detail.pack(fill="both", expand=True)
        self.buttons["swap"] = Button(
            self.detail.status_bar, text=self.t("Use result as input"), variant="ghost",
            size="small", icon="chevron-left", command=lambda: on_command("swap"), theme=theme)
        self.buttons["swap"].pack(side="right")
        self.reveal_export = Button(
            self.detail.status_bar,
            text=self.t("Show in folder"),
            variant="ghost",
            size="small",
            command=self._reveal_export,
            theme=theme,
        )
        self.export_status = Label(
            self.detail.status_bar,
            text="",
            variant="muted",
            theme=theme,
        )
        self.export_tooltip = Tooltip(self.export_status, text="", theme=theme)
        self.detail.set_content(
            self.t("Output (formatted result)"), self.t("No result yet"), "code"
        )
        self.split.add(input_card, weight=1)
        self.split.add(output_card, weight=1)
        self.form = _JSONValues(self.editor, self.indent_var, self.sort_var)
        self._update_input_count()

    def _update_input_count(self, _event=None):
        value = self.editor.get("1.0", "end-1c")
        self.input_count.configure(text=f"{len(value)} {self.t('characters')}")
        try:
            self.editor.text.edit_modified(False)
        except tk.TclError:
            pass

    @property
    def command_buttons(self):
        return list(self.buttons.values())

    def _show_options(self):
        self.options.toggle(focus=self.indent_control)

    def result_text(self):
        return self.detail.text.get("1.0", "end-1c")

    def show_export_success(self, path):
        self.export_path = Path(path)
        self.export_status.configure(text=f"{self.t('Exported')}: {self.export_path.name}")
        self.export_tooltip.set_text(str(self.export_path))
        self.reveal_export.pack(side="right", padx=(8, 0))
        self.export_status.pack(side="right")

    def clear_export_feedback(self):
        self.export_path = None
        self.export_status.pack_forget()
        self.reveal_export.pack_forget()

    def _reveal_export(self):
        if self.export_path is not None:
            self.on_reveal_export(self.export_path)

    def clear(self):
        self.clear_export_feedback()
        self.editor.delete("1.0", "end")
        self.detail.set_content(
            self.t("Output (formatted result)"), self.t("No result yet"), "code"
        )
        self.output_badge.configure(text=self.t("Waiting"))


class _ResultLabel(Label):
    def set_content(self, title, body, _format=None):
        self.configure(text=title + ("\n" + body if body else ""))


class ImageCompressorView(PaddedSurface):
    """A continuous batch workflow: add, inspect, tune, and compress."""

    def __init__(
        self,
        master,
        *,
        translate,
        on_command,
        on_preview,
        on_discard,
        on_open_directory,
        on_state_change,
        on_drop,
        dnd_available,
        theme,
    ):
        super().__init__(master, theme=theme)
        self.t = translate
        self.on_preview = on_preview
        self.on_discard = on_discard
        self.on_open_directory = on_open_directory
        self.on_state_change = on_state_change
        self.on_drop = on_drop
        self.dnd_available = dnd_available
        self.files: list[str] = []
        self.file_results: dict[str, dict] = {}
        self.output_directories: list[Path] = []
        self._batch_paths: list[str] = []
        self._needs_recompress = False
        self._busy = False
        self.selected_path: str | None = None
        self._photos: list[Any] = []
        self._preview_originals: dict[str, Image.Image] = {}
        self._preview_paths: tuple[Path, Path] | None = None
        self._preview_resize_job = None
        self._preview_size = None
        self._render_signature = None
        self._settings_job = None
        self._status_icons: dict[str, Any] = {}
        self.preview_mode = tk.StringVar(master=self, value="after")
        self.variables = {
            "format": tk.StringVar(master=self, value="JPEG"),
            "quality": tk.DoubleVar(master=self, value=82),
            "max_width": tk.StringVar(master=self, value="0"),
            "max_height": tk.StringVar(master=self, value="0"),
            "keep_metadata": tk.StringVar(master=self, value="0"),
            "keep_larger": tk.StringVar(master=self, value="0"),
            "background": tk.StringVar(master=self, value="#FFFFFF"),
        }
        heading = _page_header(
            self,
            title=self.t("Image Compressor"),
            subtitle=self.t("Compress images efficiently and reduce file size"),
            icon="image",
            theme=theme,
        )
        heading.pack(fill="x", padx=28, pady=(24, 18))
        toolbar = Toolbar(self, theme=theme, padding=(0, 16))
        self.toolbar = toolbar
        toolbar.pack(fill="x", padx=28)
        self.buttons = {}
        for title, command, variant, icon in (
            ("Add images", "import_images", "primary", "plus"),
            ("Compress images", "compress", "primary", "check"),
        ):
            button = Button(
                toolbar,
                text=self.t(title),
                command=lambda value=command: on_command(value),
                theme=theme,
                variant=variant,
                icon=icon,
            )
            button.pack(side="left" if command == "import_images" else "right", padx=(0, 10))
            self.buttons[command] = button
        self.completed_status = Badge(
            toolbar,
            text=self.t("Completed"),
            variant="secondary",
            compound="left",
            padding=(theme.px(12), theme.px(8)),
            theme=theme,
        )
        self.queue_count = Label(
            toolbar,
            text=self.t("No images selected"),
            variant="muted",
            surface="background",
            theme=theme,
        )
        self.queue_count.pack(side="left", padx=12)
        self.clear_button = Button(
            toolbar,
            text=self.t("Clear list"),
            command=self.clear_batch,
            variant="ghost",
            icon="trash",
            theme=theme,
        )
        self.clear_button.pack(side="left", padx=(0, 10))

        body = PaddedSurface(self, role="background", theme=theme)
        body.pack(fill="both", expand=True, padx=28, pady=(0, 24))
        self.body = body
        body.columnconfigure(0, minsize=theme.px(230))
        body.columnconfigure(2, weight=1)
        body.columnconfigure(4, minsize=theme.px(250))
        body.rowconfigure(0, weight=1)

        self.empty_card = ContentCard(body, bordered=True, padding=28, theme=theme)
        empty_content = PaddedSurface(self.empty_card, role="card", theme=theme)
        empty_content.pack(fill="both", expand=True)
        empty_center = PaddedSurface(empty_content, role="card", theme=theme)
        empty_center.place(relx=0.5, rely=0.46, anchor="center")
        Icon(
            empty_center,
            name="image",
            size=48,
            color=theme.tokens["primary"],
            theme=theme,
        ).pack(pady=(0, 18))
        self.drop_title = Label(
            empty_center,
            text=self.t("Drag images here"),
            variant="section",
            surface="card",
            theme=theme,
        )
        self.drop_title.pack()
        Label(
            empty_center,
            text=self.t("JPEG, PNG or WebP · up to 1000 images"),
            variant="muted",
            surface="card",
            theme=theme,
        ).pack(pady=(8, 18))
        self.empty_add_button = Button(
            empty_center,
            text=self.t("Choose images"),
            command=lambda: on_command("import_images"),
            variant="primary",
            icon="plus",
            theme=theme,
        )
        self.empty_add_button.pack()
        Label(
            empty_center,
            text=self.t("Images are processed locally and never uploaded."),
            variant="muted",
            surface="card",
            theme=theme,
        ).pack(pady=(18, 0))

        self.queue_card = ContentCard(
            body, width=theme.px(230), bordered=True, padding=10, theme=theme
        )
        self.queue_card.grid_propagate(False)
        self.queue_card.pack_propagate(False)
        self.queue_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        Label(
            self.queue_card,
            text=self.t("Images"),
            variant="section",
            surface="card",
            theme=theme,
        ).pack(anchor="w", pady=(0, 12))
        self.queue = ItemList(self.queue_card, theme=theme, on_select=self._select_file)
        self.queue.pack(fill="both", expand=True)
        self.queue.tree.column("#0", width=theme.px(200), minwidth=80, stretch=True)
        queue_style = "ImageQueue." + theme.name("Treeview")
        theme.style.configure(queue_style, rowheight=theme.px(54))
        self.queue.tree.configure(style=queue_style)
        self.queue_tooltip = Tooltip(self.queue.tree, text="", theme=theme)
        self.queue.tree.bind("<Motion>", self._queue_hover, add="+")
        self.remove_button = Button(
            self.queue_card,
            text=self.t("Remove selected"),
            command=self._remove_selected,
            variant="ghost",
            icon="trash",
            theme=theme,
        )
        self.remove_button.pack(anchor="w", pady=(10, 0))
        self.preview_card = ContentCard(body, bordered=True, padding=18, theme=theme)
        self.preview_card.grid(row=0, column=2, sticky="nsew")
        preview_header = PaddedSurface(self.preview_card, role="card", theme=theme)
        preview_header.pack(fill="x")
        Label(
            preview_header,
            text=self.t("Preview"),
            variant="section",
            surface="card",
            theme=theme,
        ).pack(anchor="w")
        self.preview_toggle = SegmentedControl(
            preview_header,
            values=(
                ("before", self.t("Original")),
                ("after", self.t("Compressed")),
            ),
            variable=self.preview_mode,
            command=self._render_preview,
            theme=theme,
            spacing=6,
        )
        self.preview_toggle.pack(anchor="w", pady=(10, 0))
        self.preview_image = Label(
            self.preview_card,
            text=self.t("A compressed preview will appear automatically"),
            surface="card",
            anchor="center",
            theme=theme,
        )
        self.preview_image.pack(fill="both", expand=True, pady=(18, 10))
        self.preview_image.bind("<Configure>", self._preview_resized, add="+")
        self.preview_summary = Label(
            self.preview_card,
            text=self.t("Add one or more JPEG, PNG, or WebP images to begin."),
            variant="muted",
            surface="card",
            theme=theme,
        )
        self.preview_summary.pack(anchor="w")

        options_host = ContentCard(
            body, width=theme.px(250), bordered=True, padding=0, theme=theme
        )
        options_host.grid(row=0, column=4, sticky="nsew", padx=(12, 0))
        options_host.pack_propagate(False)
        options_scroll = ScrollArea(options_host, bordered=False, theme=theme)
        options_scroll.pack(fill="both", expand=True)
        self.options_card = PaddedSurface(options_scroll.content, padding=12, theme=theme)
        self.options_card.pack(fill="both", expand=True)
        self.option_controls: list[Any] = []
        Label(
            self.options_card,
            text=self.t("Compression settings"),
            variant="section",
            surface="background",
            theme=theme,
        ).pack(anchor="w")
        self._select(self.options_card, "Output format", "format", ("JPEG", "PNG", "WebP"))
        self._spin(self.options_card, "Quality", "quality", 1, 100)
        self._spin(self.options_card, "Maximum width", "max_width", 0, 20000)
        self._spin(self.options_card, "Maximum height", "max_height", 0, 20000)
        self._switch(self.options_card, "Keep metadata", "keep_metadata")
        self._switch(self.options_card, "Keep larger results", "keep_larger")
        Label(self.options_card, text=self.t("JPEG background color"), theme=theme).pack(
            anchor="w", pady=(10, 4)
        )
        background_entry = Entry(
            self.options_card, textvariable=self.variables["background"], theme=theme
        )
        background_entry.pack(fill="x")
        self.option_controls.append(background_entry)
        Label(
            self.options_card,
            text=self.t("Compressed files are saved beside the originals."),
            variant="muted",
            surface="background",
            wraplength=230,
            theme=theme,
        ).pack(anchor="w", pady=(18, 0))
        self.feedback = PaddedSurface(
            self,
            height=theme.px(56),
            padding=(28, 8),
            theme=theme,
        )
        self.feedback.pack_propagate(False)
        self.batch_progress = ProgressView(self.feedback, theme=theme)
        self.result = _ResultLabel(
            self.feedback,
            text=self.t("Compressed files are saved beside the originals."),
            surface="background",
            theme=theme,
        )
        self.result.pack(side="left", fill="x", expand=True)
        self.open_output = Button(
            self.feedback,
            text=self.t("Open output folder"),
            command=self._open_output,
            variant="ghost",
            theme=theme,
        )
        self.output_tooltip = Tooltip(self.open_output, text="", theme=theme)
        self.next_batch = Button(
            self.feedback,
            text=self.t("Clear and start next batch"),
            command=self.clear_batch,
            variant="secondary",
            theme=theme,
        )
        self._build_status_icons()
        for variable in self.variables.values():
            variable.trace_add("write", self._settings_changed)
        self._setup_drop_targets()
        self._sync_layout()

    def _refresh_theme(self):
        super()._refresh_theme()
        if hasattr(self, "queue"):
            self._build_status_icons()
            self._update_queue()

    def _build_status_icons(self):
        success = "#3FB950" if self.theme.mode == "dark" else "#238636"
        specifications = {
            "pending": ("minus", self.theme.tokens["muted_foreground"]),
            "running": ("image", self.theme.tokens["primary"]),
            "completed": ("check", success),
            "skipped_larger": ("minus", self.theme.tokens["muted_foreground"]),
            "failed": ("x", self.theme.tokens["destructive"]),
            "canceled": ("x", self.theme.tokens["muted_foreground"]),
        }
        icons = {}
        for status, (name, color) in specifications.items():
            icons[status] = self.theme.icon_image(name, size=16, color=color)
        self._status_icons = icons
        if hasattr(self, "completed_status"):
            self.completed_status.configure(image=icons["completed"])

    def _queue_hover(self, event):
        path = self.queue.tree.identify_row(event.y)
        result = self.file_results.get(path, {})
        self.queue_tooltip.set_text(path + ("\n" + result.get("output", "") if result.get("output") else "")
                                    + ("\n" + result.get("message", "") if result.get("message") else ""))

    def _update_queue(self):
        labels = {"pending": "Pending", "running": "Compressing", "completed": "Saved",
                  "skipped_larger": "Skipped: no reduction", "failed": "Failed", "canceled": "Canceled"}
        self.queue.set_items([Item(path, Path(path).name) for path in self.files])
        for path in self.files:
            name = Path(path).name
            title = name[:24] + ("…" if len(name) > 24 else "")
            result = self.file_results.get(path, {})
            status_key = result.get("status", "pending")
            status = self.t(labels.get(status_key, "Pending"))
            if status_key == "completed" and result.get("original_bytes"):
                reduction = 100 * (1 - result["output_bytes"] / result["original_bytes"])
                status += f" · +{-reduction:.0f}%" if reduction < 0 else f" · −{reduction:.0f}%"
            self.queue.tree.item(
                path,
                text=title + "\n" + status,
                image=self._status_icons.get(status_key, ""),
            )
        if self.files:
            self.queue_count.configure(
                text=f"{len(self.pending_paths())} {self.t('Pending')} · "
                f"{len(self.files)} {self.t('images selected')}"
            )

    def pending_paths(self):
        terminal = {"completed", "skipped_larger"}
        return [
            path
            for path in self.files
            if self.file_results.get(path, {}).get("status") not in terminal
        ]

    def begin_batch(self, paths, on_cancel):
        self._batch_paths = list(paths)
        for path in self._batch_paths:
            self.file_results.pop(path, None)
        self._update_queue()
        self.open_output.pack_forget()
        self.next_batch.pack_forget()
        self.result.pack_forget()
        self.batch_progress.cancel.configure(command=on_cancel)
        self.batch_progress.cancel.pack(anchor="e")
        self.batch_progress.pack(fill="x", expand=True)
        self.batch_progress.update_progress(0, self.t("Compressing"))

    def batch_update(self, data, fraction=None):
        for item in data.get("items", []):
            if item.get("source") in self.files:
                self.file_results[item["source"]] = item
        current = data.get("current")
        if current in self.files:
            self.file_results[current] = {"status": "running"}
        self._update_queue()
        self.batch_progress.update_progress(
            fraction, f"{len(data.get('items', []))}/{len(self._batch_paths)}"
        )

    def finish_batch(self, data):
        self.batch_update(data, 1)
        self._batch_paths = []
        self._needs_recompress = False
        self.batch_progress.pack_forget()
        results = list(self.file_results.values())
        saved = [r for r in results if r.get("status") == "completed"]
        skipped = sum(r.get("status") == "skipped_larger" for r in results)
        failed = sum(r.get("status") == "failed" for r in results)
        canceled = sum(r.get("status") == "canceled" for r in results)
        saved_bytes = sum(r["original_bytes"] - r["output_bytes"] for r in saved)
        self.output_directories = list(dict.fromkeys(Path(r["output"]).parent for r in saved))
        summary = f"{self.t('Saved')} {len(saved)} · {self.t('Skipped')} {skipped} · {self.t('Failed')} {failed}"
        if canceled:
            summary += f" · {self.t('Canceled')} {canceled}"
        space_label = self.t("Space saved" if saved_bytes >= 0 else "Space added")
        summary += f" · {space_label}: {_format_bytes(abs(saved_bytes))}"
        if self.output_directories:
            directories = "; ".join(map(str, self.output_directories))
            self.output_tooltip.set_text(self.t("Saved to") + ": " + directories)
            self.open_output.pack(side="right")
        self.next_batch.pack(side="right", padx=(8, 0))
        self.result.configure(text=summary, wraplength=max(300, self.winfo_width() - 60))
        self.result.pack(side="left", fill="x", expand=True)
        self.on_state_change()

    def _open_output(self):
        selected = self.file_results.get(self.selected_path or "", {}).get("output")
        directories = [Path(selected).parent] if selected else self.output_directories
        for directory in directories:
            self.on_open_directory(directory)

    def _select(self, master, title, key, values):
        Label(master, text=self.t(title), theme=self.theme).pack(anchor="w", pady=(10, 4))
        control = Select(
            master,
            textvariable=self.variables[key],
            values=values,
            state="readonly",
            theme=self.theme,
        )
        control.pack(fill="x")
        self.option_controls.append(control)

    def _spin(self, master, title, key, start, end):
        Label(master, text=self.t(title), theme=self.theme).pack(anchor="w", pady=(10, 4))
        control = Spinbox(
            master,
            textvariable=self.variables[key],
            from_=start,
            to=end,
            theme=self.theme,
        )
        control.pack(fill="x")
        self.option_controls.append(control)

    def _switch(self, master, title, key):
        control = Switch(
            master,
            text=self.t(title),
            variable=self.variables[key],
            onvalue="1",
            offvalue="0",
            theme=self.theme,
        )
        control.pack(anchor="w", pady=(10, 0))
        self.option_controls.append(control)

    def _settings_changed(self, *_args):
        if self.file_results:
            self._needs_recompress = True
            self.file_results = {}
            self.output_directories = []
            self._update_queue()
            self._show_ready_feedback()
            self.on_state_change()
        if self._settings_job is not None:
            self.after_cancel(self._settings_job)
        self._settings_job = self.after(350, self._request_preview)

    def _request_preview(self):
        self._settings_job = None
        if self.selected_path:
            self.on_preview()

    def _select_file(self, path):
        if not path or path == self.selected_path:
            return
        self.selected_path = path
        self._clear_preview_images()
        self._preview_paths = None
        self._photos = []
        self.preview_image.configure(image="", text=self.t("Loading preview…"))
        self.on_preview()

    def _remove_selected(self):
        if not self.selected_path:
            return
        removed = [self.selected_path]
        remaining = [path for path in self.files if path != self.selected_path]
        self.set_files(remaining)
        self.on_discard(removed)
        self.on_state_change()

    def clear_batch(self):
        if self._busy or not self.files:
            return
        removed = list(self.files)
        self.set_files([])
        self.on_discard(removed)
        self.on_state_change()

    def _clear_preview_images(self):
        self._render_signature = None
        for original in self._preview_originals.values():
            original.close()
        self._preview_originals.clear()

    def destroy(self):
        for job in (self._preview_resize_job, self._settings_job):
            if job is not None:
                self.after_cancel(job)
        self._clear_preview_images()
        self._photos.clear()
        super().destroy()

    def _preview_resized(self, _event=None):
        if not self._preview_paths:
            return
        size = (self.preview_image.winfo_width(), self.preview_image.winfo_height())
        if size == self._preview_size:
            return
        self._preview_size = size
        if self._preview_resize_job is not None:
            self.after_cancel(self._preview_resize_job)
        self._preview_resize_job = self.after(80, self._render_preview)

    def _render_preview(self):
        self._preview_resize_job = None
        if not self._preview_paths:
            return
        width = max(120, self.preview_image.winfo_width() - 24)
        height = max(120, self.preview_image.winfo_height() - 12)
        path = self._preview_paths[0 if self.preview_mode.get() == "before" else 1]
        signature = (str(path), width, height)
        if signature == self._render_signature:
            return
        try:
            original = self._preview_originals.get(str(path))
            if original is None:
                with Image.open(path) as source:
                    original = source.copy()
                self._preview_originals[str(path)] = original
            resized = original.copy()
            resized.thumbnail((width, height), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(resized, master=self)
            resized.close()
            self.preview_image.configure(image=photo, text="")
            self._photos = [photo]
            self._render_signature = signature
        except (OSError, tk.TclError):
            self.preview_image.configure(text=Path(path).name, image="")
            self._photos = []

    def _setup_drop_targets(self):
        if not self.dnd_available:
            return
        def descendants(widget):
            yield widget
            for child in widget.winfo_children():
                yield from descendants(child)

        # TkDND resolves the widget directly beneath the pointer. Register the
        # visible children too, otherwise labels or the Treeview can mask the
        # card-level target during a real Finder drag.
        targets = [*descendants(self.empty_card), *descendants(self.queue_card)]
        for target in targets:
            register = getattr(target, "drop_target_register")
            bind = getattr(target, "dnd_bind")
            register("DND_Files")
            bind("<<DropEnter>>", self._drop_enter)
            bind("<<DropLeave>>", self._drop_leave)
            bind("<<Drop>>", self._drop_files)

    def _drop_enter(self, _event):
        if self._busy:
            return "refuse_drop"
        target = self.queue_card if self.files else self.empty_card
        target.configure(borderwidth=self.theme.px(2))
        if not self.files:
            self.drop_title.configure(text=self.t("Release to add images"))
        return "copy"

    def _drop_leave(self, _event):
        self.empty_card.configure(borderwidth=self.theme.px(1))
        self.queue_card.configure(borderwidth=self.theme.px(1))
        self.drop_title.configure(text=self.t("Drag images here"))
        return "copy"

    def _drop_files(self, event):
        self._drop_leave(event)
        if self._busy:
            return "refuse_drop"
        paths = list(self.tk.splitlist(event.data))
        return "copy" if self.on_drop(paths) else "refuse_drop"

    def _show_ready_feedback(self):
        if not self.files:
            return
        self.batch_progress.pack_forget()
        self.open_output.pack_forget()
        self.next_batch.pack_forget()
        count = len(self.pending_paths())
        self.result.configure(
            text=f"{count} {self.t('images ready to compress')}",
            wraplength=max(300, self.winfo_width() - 60),
        )
        if not self.result.winfo_manager():
            self.result.pack(side="left", fill="x", expand=True)

    def _sync_layout(self):
        if self.files:
            self.empty_card.grid_remove()
            self.queue_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
            self.preview_card.grid(row=0, column=2, sticky="nsew")
            if not self.toolbar.winfo_manager():
                self.toolbar.pack(fill="x", padx=28, before=self.body)
            if not self.feedback.winfo_manager():
                self.feedback.pack(side="bottom", fill="x", before=self.body)
        else:
            self.queue_card.grid_remove()
            self.preview_card.grid_remove()
            self.empty_card.grid(row=0, column=0, columnspan=3, sticky="nsew", padx=(0, 12))
            self.toolbar.pack_forget()
            self.feedback.pack_forget()

    def set_busy(self, busy):
        self._busy = bool(busy)
        state = ["disabled"] if busy else ["!disabled"]
        self.empty_add_button.state(state)
        self.clear_button.state(state)
        self.remove_button.state(state)
        for control in self.option_controls:
            control.state(state)

    def compression_label(self):
        pending = self.pending_paths()
        if not self.files:
            return self.t("Compress images")
        if not pending:
            return self.t("Completed")
        if self._needs_recompress:
            return self.t("Recompress")
        if any(
            self.file_results.get(path, {}).get("status") in ("failed", "canceled")
            for path in pending
        ):
            return self.t("Retry failed images")
        return self.t("Compress images")

    def sync_compression_action(self):
        completed = bool(self.files and not self.pending_paths())
        button = self.buttons["compress"]
        if completed:
            button.pack_forget()
            if not self.completed_status.winfo_manager():
                self.completed_status.pack(side="right", padx=(0, 10))
        else:
            self.completed_status.pack_forget()
            if not button.winfo_manager():
                button.pack(side="right", padx=(0, 10))

    def arguments(self):
        def dimension(name):
            value = int(float(self.variables[name].get() or 0))
            return value or None

        return {
            "paths": self.pending_paths(),
            "format": self.variables["format"].get().casefold(),
            "quality": int(float(self.variables["quality"].get() or 82)),
            "max_width": dimension("max_width"),
            "max_height": dimension("max_height"),
            "preserve_metadata": self.variables["keep_metadata"].get() == "1",
            "keep_larger": self.variables["keep_larger"].get() == "1",
            "jpeg_background": self.variables["background"].get().strip() or None,
        }

    def preview_arguments(self):
        arguments = self.arguments()
        arguments.pop("paths")
        arguments["path"] = self.selected_path or (self.files[0] if self.files else "")
        return arguments

    def set_files(self, paths):
        previous = set(self.files)
        self.files = list(dict.fromkeys(str(Path(path).resolve()) for path in paths))
        self.file_results = {p: r for p, r in self.file_results.items() if p in self.files}
        self._update_queue()
        self.buttons["import_images"].configure(variant="secondary" if self.files else "primary")
        if not self.files:
            self.queue_count.configure(text=self.t("No images selected"))
        if not self.files:
            self.file_results = {}
            self.output_directories = []
            self._batch_paths = []
            self._needs_recompress = False
            self.selected_path = None
            self._clear_preview_images()
            self._photos = []
            self._preview_paths = None
            self.preview_image.configure(
                image="", text=self.t("A compressed preview will appear automatically")
            )
            self.preview_summary.configure(
                text=self.t("Add one or more JPEG, PNG, or WebP images to begin.")
            )
            self.batch_progress.pack_forget()
            self.open_output.pack_forget()
            self.next_batch.pack_forget()
            self.result.configure(
                text=self.t("Compressed files are saved beside the originals.")
            )
            self._sync_layout()
            return
        if set(self.files) != previous:
            self._show_ready_feedback()
        self._sync_layout()
        selected = self.selected_path if self.selected_path in self.files else self.files[0]
        self.selected_path = None
        self.queue.tree.selection_set(selected)
        self.queue.tree.focus(selected)
        self._select_file(selected)

    def show_preview(self, before, after, metadata):
        paths = (Path(before), Path(after))
        if paths != self._preview_paths:
            self._clear_preview_images()
        self._preview_paths = paths
        self.update_idletasks()
        self._render_preview()
        self.preview_summary.configure(text=metadata)


class GenericToolView(Frame):
    def __init__(self, master, *, fields, title, on_run, theme):
        super().__init__(master, theme=theme)
        card = ContentCard(self, theme=theme)
        card.pack(fill="both", expand=True, padx=18, pady=18)
        Label(card, text=title, theme=theme).pack(anchor="w", pady=(0, 10))
        self.form = Form(card, fields=fields, theme=theme)
        self.form.pack(fill="both", expand=True)
        Button(card, text=title, command=on_run, theme=theme, variant="primary").pack(
            anchor="w", pady=(10, 0)
        )
        self.detail = DetailView(card, theme=theme)
        self.detail.pack(fill="both", expand=True, pady=(12, 0))


class PluginManagerView(Frame):
    """Installed-plugin browser with a bounded list and structured detail card."""

    def __init__(
        self,
        master,
        *,
        translate,
        on_home,
        on_install,
        on_restore,
        on_manage,
        theme,
        bundled_plugin_ids,
        data_root,
    ):
        super().__init__(master, theme=theme)
        self.t, self.bundled_plugin_ids = translate, set(bundled_plugin_ids)
        self.data_root = Path(data_root)
        self.running_plugins: set[str] = set()
        self.records: dict[str, dict[str, Any]] = {}
        self._all_records: tuple[dict[str, Any], ...] = ()
        self._filter = "all"

        header = _page_header(
            self,
            title=self.t("Plugin center"),
            subtitle=self.t("Manage installed local tools and their data access."),
            icon="plugin",
            theme=theme,
        )
        self.home_button = Button(
            header,
            text=self.t("Home"),
            icon="home",
            variant="ghost",
            command=on_home,
            theme=theme,
        )
        self.home_button.configure(icon="chevron-left")
        self.home_button.pack(side="left", before=header.winfo_children()[0], padx=(0, 16))
        header.pack(fill="x", padx=28, pady=(28, 18))
        controls = Toolbar(self, theme=theme, padding=(0, 12))
        controls.pack(fill="x", padx=28, pady=(0, 8))
        self.install_button = Button(
            controls,
            text=self.t("Install local bundle"),
            command=on_install,
            theme=theme,
            variant="primary",
            icon="upload",
        )
        self.install_button.pack(side="right")
        self.restore_button = Button(
            controls,
            text=self.t("Restore default tools"),
            command=on_restore,
            theme=theme,
            variant="secondary",
        )
        self.search = SearchEntry(
            controls,
            on_change=self._search,
            placeholder=self.t("Search installed plugins"),
            theme=theme,
            width=25,
        )
        self.search.pack(side="left")
        self.filter_var = tk.StringVar(master=self, value="all")
        self.filter_control = SegmentedControl(
            controls,
            values=(
                ("all", self.t("All")),
                ("enabled", self.t("Enabled")),
                ("disabled", self.t("Disabled")),
            ),
            variable=self.filter_var,
            command=lambda: self._set_filter(self.filter_var.get()),
            theme=theme,
            spacing=6,
        )
        self.filter_control.pack(side="left", padx=(12, 0))

        content = PaddedSurface(self, role="background", theme=theme)
        content.pack(fill="both", expand=True, padx=28, pady=(0, 28))
        content.columnconfigure(0, minsize=266)
        content.columnconfigure(1, weight=0)
        content.rowconfigure(0, weight=1)

        list_card = ContentCard(content, theme=theme, width=266, padding=8)
        self.local_sidebar = list_card
        list_card.grid_propagate(False)
        list_card.pack_propagate(False)
        list_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        list_header = PaddedSurface(list_card, role="card", padding=(8, 12), theme=theme)
        list_header.pack(fill="x")
        Label(
            list_header,
            text=self.t("Installed plugins"),
            variant="section",
            surface="sidebar",
            theme=theme,
        ).pack(side="left")
        self.count_badge = Badge(list_header, text="0", variant="secondary", theme=theme)
        self.count_badge.pack(side="right")
        self.plugin_list = ItemList(list_card, theme=theme, on_select=self._selected)
        self.plugin_list.pack(fill="both", expand=True, pady=(8, 0))
        self._refresh_theme()
        self.plugin_list.tree.column("#0", width=242, minwidth=100, stretch=True)

        Separator(content, orient="vertical", theme=theme).grid(row=0, column=1, sticky="ns")
        content.columnconfigure(2, weight=1)
        self.detail_card = ContentCard(content, padding=22, theme=theme)
        self.detail_card.grid(row=0, column=2, sticky="nsew")
        detail_header = PaddedSurface(self.detail_card, role="card", theme=theme)
        detail_header.pack(fill="x")
        Icon(
            detail_header,
            name="plugin",
            size=34,
            color=theme.tokens["primary"],

            theme=theme,
        ).pack(side="left", padx=(0, 14))
        names = PaddedSurface(detail_header, role="card", theme=theme)
        names.pack(side="left", fill="x", expand=True)
        self.name_label = Label(names, variant="section", wraplength=280, theme=theme)
        self.name_label.pack(anchor="w")
        self.enabled_badge = Label(
            names, text="●  " + self.t("Enabled"), variant="muted", theme=theme
        )
        self.disabled_badge = Label(
            names, text="○  " + self.t("Disabled"), variant="muted", theme=theme
        )
        self.enable_button = Button(
            detail_header,
            text=self.t("Enable"),
            command=lambda: on_manage("enable"),
            theme=theme,
            variant="primary",
        )
        self.disable_button = Button(
            detail_header,
            text=self.t("Disable"),
            command=lambda: on_manage("disable"),
            theme=theme,
            variant="secondary",
        )

        Separator(self.detail_card, theme=theme).pack(fill="x", pady=(18, 10))
        self.danger_actions = PaddedSurface(self.detail_card, role="card", theme=theme)
        self.danger_actions.pack(side="bottom", fill="x", pady=(14, 0))
        details = ScrollArea(self.detail_card, theme=theme)
        details.canvas.configure(highlightthickness=0, borderwidth=0)
        details.pack(fill="both", expand=True)
        self.details_body = details.content
        self.details_body.configure(padding=(2, 8))
        self.description_label = Label(
            self.details_body, variant="muted", wraplength=440, theme=theme
        )
        self.commands_label = Label(self.details_body, variant="muted", wraplength=440, theme=theme)
        self.summary_label = Label(
            self.details_body,
            text=self.t("Plugin details"),
            variant="section",
            theme=theme,
        )
        self.version_label = Label(self.details_body, theme=theme)
        self.id_label = Label(self.details_body, variant="muted", theme=theme)
        self.source_label = Label(self.details_body, theme=theme)
        self.runtime_label = Label(self.details_body, theme=theme)
        self.data_label = Label(self.details_body, variant="muted", theme=theme, wraplength=700)
        self.capabilities_label = Label(
            self.details_body, variant="muted", theme=theme, wraplength=700
        )
        self.summary_label.pack(anchor="w", pady=(8, 12))
        self.description_label.pack(anchor="w", pady=(0, 18), before=self.summary_label)
        for detail_label in (self.version_label, self.source_label, self.runtime_label):
            detail_label.pack(anchor="w", pady=(0, 8))
        self.access_label = Label(
            self.details_body,
            text=self.t("Data and permissions"),
            variant="section",
            theme=theme,
        )
        self.commands_label.pack(anchor="w", pady=(8, 12))
        self.access_label.pack(anchor="w", pady=(20, 12))
        for detail_label in (self.id_label, self.data_label, self.capabilities_label):
            detail_label.pack(anchor="w", pady=(0, 7))
        self.disable_hint = Label(
            self.details_body,
            text=self.t("Disabling removes this plugin from home, the sidebar, and search."),
            variant="muted",
            theme=theme,
            wraplength=700,
        )
        self.action_separator = Separator(self.danger_actions, theme=theme)
        self.danger_label = Label(
            self.danger_actions, text=self.t("Danger zone"), variant="section", theme=theme
        )
        self.uninstall_button = Button(
            self.danger_actions,
            text=self.t("Uninstall"),
            command=lambda: on_manage("uninstall"),
            theme=theme,
            variant="outline",
            icon="trash",
        )
        self.delete_button = Button(
            self.danger_actions,
            text=self.t("Delete saved data"),
            command=lambda: on_manage("delete"),
            theme=theme,
            variant="destructive",
            icon="trash",
        )
        self.details_body.bind("<Configure>", self._wrap_details, add="+")
        self._show_empty()

    def _refresh_theme(self):
        if not hasattr(self, "plugin_list"):
            return
        theme = self.theme
        list_style = theme.name("Plugin.Treeview")
        theme.style.configure(
            list_style,
            rowheight=theme.px(68),

            fieldbackground=theme.tokens["card"],
        )
        theme.style.map(
            list_style,
            background=[("selected", theme.tokens["accent"])],
            foreground=[("selected", theme.tokens["accent_foreground"])],
        )
        self.plugin_list.tree.configure(style=list_style)

    def _wrap_details(self, event):
        for label in (
            self.data_label,
            self.capabilities_label,
            self.id_label,
            self.disable_hint,
            self.description_label,
            self.commands_label,
        ):
            label.configure(wraplength=max(180, event.width - 28))

    def _set_filter(self, value):
        self._filter = value
        self._apply_filter()

    def _search(self, _text):
        self._apply_filter()

    def _apply_filter(self):
        query = self.search.get().casefold().strip()
        records = [
            r
            for r in self._all_records
            if (self._filter == "all" or bool(r["enabled"]) == (self._filter == "enabled"))
            and query in (r["id"] + " " + r["manifest"]["name"]).casefold()
        ]
        self.records = {r["id"]: r for r in records}
        self.count_badge.configure(text=str(len(records)))
        self.plugin_list.set_items(
            [
                Item(
                    r["id"],
                    r["manifest"]["name"],
                    (self.t("Enabled") if r["enabled"] else self.t("Disabled"))
                    + " · "
                    + r["manifest"]["version"],
                )
                for r in records
            ]
        )
        for record in records:
            self.plugin_list.tree.item(
                record["id"],
                text=f"{record['manifest']['name']}\n{self.t('Enabled') if record['enabled'] else self.t('Disabled')}  ·  {record['manifest']['version']}",
            )
        ids = tuple(self.records)
        if ids:
            selected = self.plugin_list.selected_id()
            if selected not in self.records:
                selected = ids[0]
                self.plugin_list.tree.selection_set(selected)
            # ItemList may preserve or establish a selection without emitting its
            # callback, so always keep the detail pane synchronized explicitly.
            self._selected(selected)
        elif not ids:
            self._show_empty()

    def _show_empty(self):
        self.name_label.configure(text=self.t("Select a plugin"))
        for label in (
            self.description_label,
            self.commands_label,
            self.version_label,
            self.id_label,
            self.source_label,
            self.runtime_label,
            self.data_label,
            self.capabilities_label,
        ):
            label.configure(text="")
            label.pack_forget()
        self.summary_label.pack_forget()
        self.access_label.pack_forget()
        for widget in (
            self.enabled_badge,
            self.disabled_badge,
            self.disable_hint,
            self.action_separator,
            self.enable_button,
            self.disable_button,
            self.danger_label,
            self.uninstall_button,
            self.delete_button,
        ):
            widget.pack_forget()

    def _selected(self, identifier):
        record = self.records.get(identifier)
        if record is None:
            self._show_empty()
            return
        manifest = record["manifest"]
        self.name_label.configure(text=manifest["name"])
        self.description_label.configure(
            text=self.t(
                manifest.get("description")
                or "All processing happens locally. Your data never leaves this device."
            )
        )
        commands = record.get("descriptor", {}).get("commands", [])
        self.commands_label.configure(
            text="  ·  ".join(self.t(command.get("title", command["id"])) for command in commands)
        )
        self.description_label.pack_forget()
        self.version_label.configure(text=f"{self.t('Version')}: {manifest['version']}")
        self.id_label.configure(text=f"{self.t('Plugin ID')}: {record['id']}")
        self.source_label.configure(
            text=f"{self.t('Source')}: {self.t('Built in') if record['id'] in self.bundled_plugin_ids else self.t('Local bundle')}"
        )
        self.runtime_label.configure(
            text=f"{self.t('Runtime status')}: {self.t('Running') if record['id'] in self.running_plugins else self.t('Idle')}"
        )
        self.data_label.configure(
            text=f"{self.t('Data location')}: {self.data_root / 'plugin-data' / record['id']}"
        )
        self.capabilities_label.configure(
            text=f"{self.t('Capabilities')}: {', '.join(manifest.get('capabilities', ())) or self.t('None')}"
        )
        self.enabled_badge.pack_forget()
        self.disabled_badge.pack_forget()
        self.summary_label.pack(anchor="w", pady=(8, 12))
        self.description_label.pack(anchor="w", pady=(0, 18), before=self.summary_label)
        for detail_label in (self.version_label, self.source_label, self.runtime_label):
            detail_label.pack(anchor="w", pady=(0, 8))
        self.commands_label.pack(anchor="w", pady=(8, 12))
        self.access_label.pack(anchor="w", pady=(20, 12))
        for detail_label in (self.id_label, self.data_label, self.capabilities_label):
            detail_label.pack(anchor="w", pady=(0, 7))
        (self.enabled_badge if record["enabled"] else self.disabled_badge).pack(
            anchor="w", pady=(5, 0)
        )
        self.disable_hint.pack(anchor="w", pady=(6, 12))
        self.action_separator.pack(fill="x", pady=(12, 16))
        self.enable_button.pack_forget()
        self.disable_button.pack_forget()
        (self.disable_button if record["enabled"] else self.enable_button).pack(
            side="right", padx=(8, 0), before=self.name_label.master
        )
        self.danger_label.pack(side="left")
        self.uninstall_button.pack(side="right", padx=(8, 0))
        self.delete_button.pack(side="right")

    def set_records(self, records: list[dict[str, Any]] | tuple[dict[str, Any], ...]):
        records = tuple(records)
        if records == self._all_records:
            return
        self._all_records = records
        self._apply_filter()
        installed = {record["id"] for record in self._all_records}
        if self.bundled_plugin_ids <= installed:
            self.restore_button.pack_forget()
        else:
            self.restore_button.pack(side="right", padx=(0, 10))

    def set_running(self, identifiers):
        running = set(identifiers)
        if running == self.running_plugins:
            return
        self.running_plugins = running
        selected = self.selected_id()
        if selected:
            self._selected(selected)

    def selected_id(self):
        return self.plugin_list.selected_id()

    def set_busy(self, busy):
        state = ["disabled"] if busy else ["!disabled"]
        for widget in (
            self.install_button,
            self.restore_button,
            self.enable_button,
            self.disable_button,
            self.uninstall_button,
            self.delete_button,
        ):
            widget.state(state)


class SettingsView(PaddedSurface):
    """Categorized settings page with its own local navigation."""

    LANGUAGE_IDS = ("system", "en", "zh-CN")
    MODE_IDS = ("system", "light", "dark")

    def __init__(
        self,
        master,
        *,
        translate,
        language_preference,
        mode_preference,
        recent_enabled,
        on_home,
        on_language,
        on_mode,
        on_recent,
        on_open_data,
        on_clear_logs,
        data_path,
        version,
        theme,
    ):
        super().__init__(master, theme=theme)
        self.t = translate
        self.language_var = tk.StringVar(master=self)
        self.mode_var = tk.StringVar(master=self)
        self.recent_var = tk.StringVar(master=self, value="1" if recent_enabled else "0")

        header = _page_header(
            self,
            title=self.t("Settings"),
            subtitle=self.t("Make PyDeskTools work the way you prefer."),
            icon="settings",
            theme=theme,
        )
        self.home_button = Button(
            header,
            text=self.t("Home"),
            icon="home",
            variant="ghost",
            command=on_home,
            theme=theme,
        )
        self.home_button.configure(icon="chevron-left")
        self.home_button.pack(side="left", before=header.winfo_children()[0], padx=(0, 16))
        header.pack(fill="x", padx=28, pady=(24, 18))
        body = PaddedSurface(self, role="background", theme=theme)
        body.pack(fill="both", expand=True, padx=28, pady=20)
        nav = ContentCard(body, theme=theme, width=184, padding=10)
        self.local_sidebar = nav
        nav.pack(side="left", fill="y", padx=(0, 14))
        nav.pack_propagate(False)
        self.nav_buttons = {}
        for label, target, icon in (
            ("General", "general", "settings"),
            ("Appearance", "appearance", "image"),
            ("Shortcuts", "shortcuts", "search"),
            ("Plugin sources", "sources", "plugin"),
            ("Storage and logs", "storage", "download"),
            ("About", "about", "check"),
        ):
            button = NavigationItem(
                nav,
                text=self.t(label),
                command=lambda value=target: self.show_section(value),
                theme=theme,
                icon=icon,
            )
            button.pack(fill="x", pady=3)
            self.nav_buttons[target] = button

        Separator(body, orient="vertical", theme=theme).pack(side="left", fill="y")
        viewport = ScrollArea(body, theme=theme, bordered=False, resize_debounce_ms=60)
        viewport.pack(side="left", fill="both", expand=True)
        self.content = viewport.content
        self.content.configure(padding=(16, 0, 8, 8))
        self.sections = {}

        general = self._section(
            "general", "Language and region", "Choose the language used throughout the app."
        )
        row = _settings_row(
            general,
            title=self.t("Language"),
            description=self.t("Choose the application interface language."),
            icon="settings",
            theme=theme,
        )
        row.pack(fill="x")
        self.language_select = Select(
            row, textvariable=self.language_var, state="readonly", width=18, theme=theme
        )
        self.language_select.pack(side="right", padx=(18, 0))
        self.language_select.bind("<<ComboboxSelected>>", lambda _event: on_language())
        Separator(general, theme=theme).pack(fill="x")
        row = _settings_row(
            general,
            title=self.t("Show recent work on home"),
            description=self.t("Keep your latest local commands within easy reach."),
            icon="download",
            theme=theme,
        )
        row.pack(fill="x")
        Switch(
            row,
            variable=self.recent_var,
            onvalue="1",
            offvalue="0",
            command=on_recent,
            theme=theme,
        ).pack(side="right", padx=(18, 0))
        Separator(general, theme=theme).pack(fill="x")
        row = _settings_row(
            general,
            title=self.t("Global quick search"),
            description=self.t("Open search anywhere inside PyDeskTools."),
            icon="search",
            theme=theme,
        )
        row.pack(fill="x")
        Badge(row, text="⌘ K  /  Ctrl K", variant="outline", theme=theme).pack(side="right")
        Alert(
            general,
            title=self.t("Local mode (offline)"),
            message=self.t("Files and command results remain on this device."),
            theme=theme,
        ).pack(fill="x", pady=(8, 0))

        appearance = self._section(
            "appearance", "Appearance", "Match the system or choose a fixed color scheme."
        )
        row = _settings_row(
            appearance,
            title=self.t("Theme"),
            description=self.t("Control the light and dark appearance of PyDeskTools."),
            icon="image",
            theme=theme,
        )
        row.pack(fill="x")
        self.mode_select = Select(
            row, textvariable=self.mode_var, state="readonly", width=18, theme=theme
        )
        self.mode_select.pack(side="right", padx=(18, 0))
        self.mode_select.bind("<<ComboboxSelected>>", lambda _event: on_mode())

        shortcuts = self._section(
            "shortcuts", "Keyboard shortcuts", "Fast access without leaving the current task."
        )
        row = _settings_row(
            shortcuts,
            title=self.t("Global quick search"),
            description=self.t("Open search anywhere inside PyDeskTools."),
            icon="search",
            theme=theme,
        )
        row.pack(fill="x")
        Badge(row, text="⌘ K  /  Ctrl K", variant="outline", theme=theme).pack(side="right")
        Separator(shortcuts, theme=theme).pack(fill="x")
        row = _settings_row(
            shortcuts,
            title=self.t("Quit PyDeskTools"),
            description=self.t("Exit the application instead of keeping it in the system tray."),
            icon="x",
            theme=theme,
        )
        row.pack(fill="x")
        Badge(row, text="⌘ Q  /  Ctrl Q", variant="outline", theme=theme).pack(side="right")

        sources = self._section(
            "sources", "Plugin sources", "This release installs local bundles only."
        )
        Alert(
            sources,
            title=self.t("Offline source"),
            message=self.t("Plugins are installed from local signed or approved bundles."),
            theme=theme,
        ).pack(fill="x")

        storage = self._section(
            "storage", "Storage and logs", "Inspect local data or clear diagnostic logs."
        )
        row = _settings_row(
            storage,
            title=self.t("Application data"),
            description=str(data_path),
            icon="download",
            theme=theme,
        )
        row.pack(fill="x")
        Button(row, text=self.t("Open data directory"), command=on_open_data, theme=theme).pack(
            side="right", padx=(18, 0)
        )
        Separator(storage, theme=theme).pack(fill="x")
        row = _settings_row(
            storage,
            title=self.t("Diagnostic logs"),
            description=self.t("Remove locally stored application logs."),
            icon="trash",
            theme=theme,
        )
        row.pack(fill="x")
        Button(
            row,
            text=self.t("Clear logs"),
            command=on_clear_logs,
            theme=theme,
            variant="destructive",
        ).pack(side="right", padx=(18, 0))

        about = self._section("about", "About", "Version and legal information.")
        row = _settings_row(
            about,
            title=f"PyDeskTools {version}",
            description=self.t("Local-first desktop tools powered by isolated plugins."),
            icon="check",
            theme=theme,
        )
        row.pack(fill="x")
        Icon(row, source=Path(__file__).parent / "assets/logo-ui.svg", size=42, theme=theme).pack(side="right", padx=16)
        Separator(about, theme=theme).pack(fill="x")
        Label(about, text=self.t("License: MIT"), theme=theme).pack(anchor="w", pady=(14, 4))
        Label(
            about,
            text=self.t("Third-party notices are included with the application."),
            variant="muted",
            theme=theme,
        ).pack(anchor="w")

        import webbrowser
        Button(about, text=self.t("Source repository"), variant="ghost",
               command=lambda: webbrowser.open("https://github.com/openHacking/PyDeskTools"),
               theme=theme).pack(anchor="w", pady=(14, 0))

        self.configure_options(language_preference, mode_preference)
        self.show_section("general")

    def _section(self, identifier, title, subtitle):
        frame = ContentCard(self.content, theme=self.theme, padding=24)
        _section_heading(
            frame,
            title=self.t(title),
            subtitle=self.t(subtitle),
            theme=self.theme,
        ).pack(fill="x", pady=(0, 14))
        Separator(frame, theme=self.theme).pack(fill="x", pady=(0, 2))
        self.sections[identifier] = frame
        return frame

    def show_section(self, identifier):
        for key, frame in self.sections.items():
            frame.pack_forget()
            self.nav_buttons[key].configure(selected=key == identifier)
        self.sections[identifier].pack(fill="x")

    def configure_options(self, language_preference, mode_preference):
        self._language_labels = (self.t("Follow system"), "English", "简体中文")
        self._mode_labels = (self.t("Follow system"), self.t("Light"), self.t("Dark"))
        self.language_select.configure(values=self._language_labels)
        self.mode_select.configure(values=self._mode_labels)
        self.language_var.set(self._language_labels[self.LANGUAGE_IDS.index(language_preference)])
        self.mode_var.set(self._mode_labels[self.MODE_IDS.index(mode_preference)])

    def language_preference(self):
        return self.LANGUAGE_IDS[self._language_labels.index(self.language_var.get())]

    def mode_preference(self):
        return self.MODE_IDS[self._mode_labels.index(self.mode_var.get())]

    def set_language_preference(self, preference):
        self.language_var.set(self._language_labels[self.LANGUAGE_IDS.index(preference)])

    def set_mode_preference(self, preference):
        self.mode_var.set(self._mode_labels[self.MODE_IDS.index(preference)])
