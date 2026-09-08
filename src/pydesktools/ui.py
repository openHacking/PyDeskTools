"""Application-owned views composed exclusively from PyDeskUI primitives."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from typing import Any, Literal

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
)

JSON_PLUGIN = "org.pydesk.json-tools"
IMAGE_PLUGIN = "org.pydesk.image-compressor"


def _page_header(master, *, title, subtitle, icon, theme):
    """Create the shared title treatment used by every workspace page."""
    header = Surface(master, role="background", theme=theme)
    Icon(
        header,
        name=icon,
        size=24,
        color=theme.tokens["primary"],
        background=master.winfo_toplevel().cget("background"),
        theme=theme,
    ).pack(
        side="left", padx=(0, 14)
    )
    copy = Surface(header, role="background", theme=theme)
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
    box = Surface(master, role="card", theme=theme)
    Label(box, text=title, variant="section", theme=theme).pack(anchor="w")
    if subtitle:
        Label(box, text=subtitle, variant="muted", theme=theme).pack(anchor="w", pady=(4, 0))
    return box


def _settings_row(master, *, title, description, icon, theme):
    row = Surface(master, role="card", theme=theme)
    Icon(row, name=icon, size=21, color=theme.tokens["muted_foreground"], theme=theme).pack(
        side="left", padx=(2, 16), pady=16
    )
    copy = Surface(row, role="card", theme=theme)
    copy.pack(side="left", fill="x", expand=True, pady=16)
    Label(copy, text=title, theme=theme).pack(anchor="w")
    Label(copy, text=description, variant="muted", theme=theme).pack(anchor="w", pady=(6, 0))
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
        super().__init__(master, theme=theme, width=188, padding=(16, 22))
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
        self.tools_host = Surface(self, role="sidebar", theme=theme)
        self.tools_host.pack(fill="x")
        Surface(self, role="sidebar", theme=theme).pack(fill="both", expand=True)
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
        status = Surface(self, role="sidebar", theme=theme)
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


class HomeView(Frame):
    """Search-first home page with bounded sections and useful empty states."""

    def __init__(
        self, master, *, translate, on_search, on_select, on_open_file, on_open_plugins, theme
    ):
        super().__init__(master, theme=theme)
        self.t = translate
        viewport = ScrollArea(self, theme=theme, resize_debounce_ms=60)
        viewport.pack(fill="both", expand=True)
        body = viewport.content
        body.configure(padding=(58, 42, 58, 48))

        self.hero = Surface(body, role="background", theme=theme)
        self.hero.pack(fill="x")
        hero_title = Surface(self.hero, role="background", theme=theme)
        hero_title.pack()
        Icon(
            hero_title,
            name="plus",
            size=28,
            color=theme.tokens["primary"],
            background=self.winfo_toplevel().cget("background"),
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
        self.search_card = Surface(self.hero, role="background", theme=theme)
        self.search_card.pack(fill="x", padx=84)
        self.search = SearchEntry(
            self.search_card,
            on_change=on_search,
            placeholder=self.t("Search tools or commands, e.g. format JSON, compress images…"),
            shortcut_hint="⌘ K",
            theme=theme,
        )
        self.search.pack(fill="x")
        self.results = ItemList(self.search_card, theme=theme, on_select=on_select)
        self.results.tree.configure(height=4)

        shortcuts = Surface(self.hero, role="background", theme=theme)
        shortcuts.pack(pady=(18, 0))
        for text, icon in (
            ("Search tools", "search"),
            ("Find commands", "check"),
            ("Open file", "upload"),
        ):
            item = Surface(shortcuts, role="background", theme=theme)
            item.pack(side="left", padx=26)
            Icon(
                item,
                name=icon,
                size=18,
                color=theme.tokens["muted_foreground"],
                background=self.winfo_toplevel().cget("background"),
                theme=theme,
            ).pack(
                side="left", padx=(0, 9)
            )
            Label(
                item,
                text=self.t(text),
                variant="muted",
                surface="background",
                theme=theme,
            ).pack(side="left")

        recent_card = Surface(body, role="background", padding=4, theme=theme)
        recent_card.pack(fill="x", pady=(38, 0))
        recent_header = Surface(recent_card, role="card", theme=theme)
        recent_header.pack(fill="x")
        Icon(
            recent_header,
            name="download",
            size=19,
            color=theme.tokens["muted_foreground"],
            background=self.winfo_toplevel().cget("background"),
            theme=theme,
        ).pack(
            side="left", padx=(0, 10)
        )
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

        guide = Surface(body, role="background", theme=theme, padding=(4, 12))
        guide.pack(fill="x", pady=(22, 0))
        guide_title = Surface(guide, role="background", theme=theme)
        guide_title.pack(fill="x")
        Icon(
            guide_title,
            name="plus",
            size=19,
            color=theme.tokens["primary"],
            background=self.winfo_toplevel().cget("background"),
            theme=theme,
        ).pack(
            side="left", padx=(0, 10)
        )
        Label(
            guide_title,
            text=self.t("Two ways to get started"),
            variant="section",
            surface="background",
            theme=theme,
        ).pack(
            side="left"
        )
        columns = Surface(guide, role="background", theme=theme)
        columns.pack(fill="x", pady=(20, 18))
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
            card = Surface(columns, role="background", padding=(4, 10), theme=theme)
            card.grid(row=0, column=target, sticky="nsew")
            Icon(
                card,
                name=icon,
                size=25,
                color=theme.tokens["primary"],
                background=self.winfo_toplevel().cget("background"),
                theme=theme,
            ).pack(
                side="left", padx=(0, 16)
            )
            copy = Surface(card, role="background", theme=theme)
            copy.pack(side="left", fill="x", expand=True)
            Label(copy, text=title, variant="section", surface="background", theme=theme).pack(
                anchor="w"
            )
            Label(
                copy,
                text=description,
                variant="muted",
                surface="background",
                wraplength=330,
                theme=theme,
            ).pack(anchor="w", pady=(6, 0))
        actions = Surface(guide, role="background", theme=theme)
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


class JSONToolView(Frame):
    """Aligned input/output workbench with one functional center divider."""

    def __init__(self, master, *, translate, on_command, theme):
        super().__init__(master, theme=theme)
        self.t = translate
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
            ("Swap", "swap", "default", "chevron-right"),
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
        self.options = Popover(self.settings_button, theme=theme)
        Label(self.options.content, text=self.t("Indent"), theme=theme).pack(anchor="w")
        Spinbox(
            self.options.content,
            textvariable=self.indent_var,
            from_=0,
            to=8,
            width=8,
            theme=theme,
        ).pack(anchor="w", pady=(4, 10))
        Switch(
            self.options.content,
            text=self.t("Sort keys"),
            variable=self.sort_var,
            onvalue="1",
            offvalue="0",
            theme=theme,
        ).pack(anchor="w")
        self.split = SplitPane(self, orient="horizontal", theme=theme)
        self.split.pack(fill="both", expand=True, padx=28, pady=(0, 24))
        input_card = Surface(self.split, role="card", theme=theme)
        input_header = Surface(input_card, role="card", padding=(16, 14), theme=theme)
        input_header.pack(fill="x")
        Label(input_header, text=self.t("Input (raw JSON)"), variant="section", theme=theme).pack(
            side="left"
        )
        self.input_count = Badge(input_header, text="0", variant="secondary", theme=theme)
        self.input_count.pack(side="right")
        editor_host = Surface(input_card, role="card", padding=(16, 12), theme=theme)
        editor_host.pack(fill="both", expand=True)
        self.editor = CodeEditor(editor_host, theme=theme)
        self.editor.pack(fill="both", expand=True)
        self.editor.insert("1.0", '{"hello": "世界"}')
        self.editor.text.bind("<<Modified>>", self._update_input_count, add="+")
        output_card = Surface(self.split, role="card", theme=theme)
        output_header = Surface(output_card, role="card", padding=(16, 14), theme=theme)
        output_header.pack(fill="x")
        Label(output_header, text=self.t("Output (formatted result)"), variant="section", theme=theme).pack(
            side="left"
        )
        self.output_badge = Badge(
            output_header, text=self.t("Waiting"), variant="secondary", theme=theme
        )
        self.output_badge.pack(side="right")
        detail_host = Surface(output_card, role="card", padding=(16, 12), theme=theme)
        detail_host.pack(fill="both", expand=True)
        self.detail = _JSONOutput(detail_host, readonly=True, theme=theme)
        self.detail.pack(fill="both", expand=True)
        self.detail.set_content(self.t("Output (formatted result)"), self.t("No result yet"), "code")
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
        self.options.show()

    def result_text(self):
        return self.detail.text.get("1.0", "end-1c")

    def swap(self):
        value = self.result_text()
        if value:
            self.editor.delete("1.0", "end")
            self.editor.insert("1.0", value)

    def clear(self):
        self.editor.delete("1.0", "end")
        self.detail.set_content(self.t("Output (formatted result)"), self.t("No result yet"), "code")
        self.output_badge.configure(text=self.t("Waiting"))


class ImageCompressorView(Frame):
    """A continuous batch workflow: add, inspect, tune, and compress."""

    def __init__(self, master, *, translate, on_command, on_preview, theme):
        super().__init__(master, theme=theme)
        self.t = translate
        self.on_preview = on_preview
        self.files: list[str] = []
        self.selected_path: str | None = None
        self._photos = []
        self._preview_paths: tuple[Path, Path] | None = None
        self._preview_resize_job = None
        self._settings_job = None
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
            button.pack(side="right", padx=(10, 0))
            self.buttons[command] = button
        self.queue_count = Label(
            toolbar,
            text=self.t("No images selected"),
            variant="muted",
            surface="background",
            theme=theme,
        )
        self.queue_count.pack(side="left")

        body = Surface(self, role="background", theme=theme)
        body.pack(fill="both", expand=True, padx=28, pady=(0, 24))
        body.columnconfigure(0, minsize=210)
        body.columnconfigure(2, weight=1)
        body.columnconfigure(4, minsize=250)
        body.rowconfigure(0, weight=1)

        self.queue_card = Surface(body, role="background", padding=(0, 4, 18, 0), theme=theme)
        self.queue_card.grid(row=0, column=0, sticky="nsew")
        Label(
            self.queue_card,
            text=self.t("Images"),
            variant="section",
            surface="background",
            theme=theme,
        ).pack(anchor="w", pady=(0, 12))
        self.queue = ItemList(self.queue_card, theme=theme, on_select=self._select_file)
        self.queue.pack(fill="both", expand=True)
        self.remove_button = Button(
            self.queue_card,
            text=self.t("Remove selected"),
            command=self._remove_selected,
            variant="ghost",
            icon="trash",
            theme=theme,
        )
        self.remove_button.pack(anchor="w", pady=(10, 0))
        self.preview_card = Surface(body, role="background", padding=(22, 4), theme=theme)
        self.preview_card.grid(row=0, column=2, sticky="nsew")
        preview_header = Surface(self.preview_card, role="background", theme=theme)
        preview_header.pack(fill="x")
        Label(
            preview_header,
            text=self.t("Preview"),
            variant="section",
            surface="background",
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
            surface="background",
            theme=theme,
        )
        self.preview_image.pack(fill="both", expand=True, pady=(18, 10))
        self.preview_image.bind("<Configure>", self._preview_resized, add="+")
        self.preview_summary = Label(
            self.preview_card,
            text=self.t("Add one or more JPEG, PNG, or WebP images to begin."),
            variant="muted",
            surface="background",
            theme=theme,
        )
        self.preview_summary.pack(anchor="w")

        self.options_card = Surface(
            body, role="background", padding=(18, 4, 0, 0), theme=theme
        )
        self.options_card.grid(row=0, column=4, sticky="nsew")
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
        Entry(self.options_card, textvariable=self.variables["background"], theme=theme).pack(
            fill="x"
        )
        Label(
            self.options_card,
            text=self.t("Compressed files are saved beside the originals."),
            variant="muted",
            surface="background",
            wraplength=230,
            theme=theme,
        ).pack(anchor="w", pady=(18, 0))
        self.result = DetailView(self.options_card, theme=theme)
        self.result.text.configure(width=24, height=4)
        self.result.pack(fill="x", pady=(18, 0))
        self.result.set_content(self.t("Results"), self.t("No result yet"))
        for variable in self.variables.values():
            variable.trace_add("write", self._settings_changed)

    def _select(self, master, title, key, values):
        Label(master, text=self.t(title), theme=self.theme).pack(anchor="w", pady=(10, 4))
        Select(
            master,
            textvariable=self.variables[key],
            values=values,
            state="readonly",
            theme=self.theme,
        ).pack(fill="x")

    def _spin(self, master, title, key, start, end):
        Label(master, text=self.t(title), theme=self.theme).pack(anchor="w", pady=(10, 4))
        Spinbox(
            master,
            textvariable=self.variables[key],
            from_=start,
            to=end,
            theme=self.theme,
        ).pack(fill="x")

    def _switch(self, master, title, key):
        Switch(
            master,
            text=self.t(title),
            variable=self.variables[key],
            onvalue="1",
            offvalue="0",
            theme=self.theme,
        ).pack(anchor="w", pady=(10, 0))

    def _settings_changed(self, *_args):
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
        self.on_preview()

    def _remove_selected(self):
        if not self.selected_path:
            return
        remaining = [path for path in self.files if path != self.selected_path]
        self.set_files(remaining)

    def _preview_resized(self, _event=None):
        if not self._preview_paths:
            return
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
        try:
            original = tk.PhotoImage(master=self, file=str(path))
            factor = max(1, (original.width() + width - 1) // width)
            factor = max(factor, (original.height() + height - 1) // height)
            photo = original.subsample(factor, factor) if factor > 1 else original
            self.preview_image.configure(image=photo, text="")
            self._photos = [photo]
        except tk.TclError:
            self.preview_image.configure(text=Path(path).name, image="")
            self._photos = []

    def arguments(self):
        def dimension(name):
            value = int(float(self.variables[name].get() or 0))
            return value or None

        return {
            "paths": list(self.files),
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
        self.files = list(dict.fromkeys(map(str, paths)))
        self.queue.set_items(
            [
                Item(path, Path(path).name, Path(path).suffix.removeprefix(".").upper())
                for path in self.files
            ]
        )
        self.queue_count.configure(
            text=(
                self.t("No images selected")
                if not self.files
                else f"{len(self.files)} {self.t('images selected')}"
            )
        )
        if not self.files:
            self.selected_path = None
            self._preview_paths = None
            self.preview_image.configure(
                image="", text=self.t("A compressed preview will appear automatically")
            )
            self.preview_summary.configure(
                text=self.t("Add one or more JPEG, PNG, or WebP images to begin.")
            )
            return
        selected = self.selected_path if self.selected_path in self.files else self.files[0]
        self.selected_path = None
        self.queue.tree.selection_set(selected)
        self.queue.tree.focus(selected)
        self._select_file(selected)

    def show_preview(self, before, after, metadata):
        self._preview_paths = (Path(before), Path(after))
        self.update_idletasks()
        self._render_preview()
        self.preview_summary.configure(text=metadata)


class GenericToolView(Frame):
    def __init__(self, master, *, fields, title, on_run, theme):
        super().__init__(master, theme=theme)
        card = Card(self, theme=theme)
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

        top_nav = Surface(self, role="background", theme=theme)
        top_nav.pack(fill="x", padx=28, pady=(18, 0))
        Button(
            top_nav,
            text=self.t("Home"),
            command=on_home,
            theme=theme,
            variant="link",
            icon="home",
        ).pack(side="left")

        header = _page_header(
            self,
            title=self.t("Plugin center"),
            subtitle=self.t("Manage installed local tools and their data access."),
            icon="plugin",
            theme=theme,
        )
        header.pack(fill="x", padx=28, pady=(12, 18))
        self.install_button = Button(
            header,
            text=self.t("Install local bundle"),
            command=on_install,
            theme=theme,
            variant="primary",
            icon="upload",
        )
        self.install_button.pack(side="right")
        self.restore_button = Button(
            header,
            text=self.t("Restore default tools"),
            command=on_restore,
            theme=theme,
            variant="secondary",
        )
        controls = Toolbar(self, theme=theme, padding=(0, 16))
        controls.pack(fill="x", padx=28)
        self.search = SearchEntry(
            controls,
            on_change=self._search,
            placeholder=self.t("Search installed plugins"),
            theme=theme,
            width=34,
        )
        self.search.pack(side="left")
        self.filter_var = tk.StringVar(master=self, value="all")
        self.filter_control = SegmentedControl(
            controls,
            values=(("all", self.t("All")), ("enabled", self.t("Enabled")), ("disabled", self.t("Disabled"))),
            variable=self.filter_var,
            command=lambda: self._set_filter(self.filter_var.get()),
            theme=theme,
            spacing=6,
        )
        self.filter_control.pack(side="left", padx=(12, 0))

        content = Surface(self, role="background", theme=theme)
        content.pack(fill="both", expand=True, padx=28, pady=(0, 28))
        content.columnconfigure(0, minsize=300)
        content.columnconfigure(1, weight=0)
        content.rowconfigure(0, weight=1)

        list_card = Sidebar(content, theme=theme, padding=(8, 4))
        list_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        list_header = Surface(list_card, role="sidebar", padding=(18, 16), theme=theme)
        list_header.pack(fill="x")
        Label(
            list_header,
            text=self.t("Installed plugins"),
            variant="section",
            surface="sidebar",
            theme=theme,
        ).pack(
            side="left"
        )
        self.count_badge = Badge(list_header, text="0", variant="secondary", theme=theme)
        self.count_badge.pack(side="right")
        self.plugin_list = ItemList(list_card, theme=theme, on_select=self._selected)
        self.plugin_list.pack(fill="both", expand=True, padx=10, pady=10)

        Separator(content, orient="vertical", theme=theme).grid(row=0, column=1, sticky="ns")
        content.columnconfigure(2, weight=1)
        self.detail_card = Surface(content, role="background", padding=(24, 4), theme=theme)
        self.detail_card.grid(row=0, column=2, sticky="nsew")
        detail_header = Surface(self.detail_card, role="background", theme=theme)
        detail_header.pack(fill="x")
        Icon(
            detail_header,
            name="plugin",
            size=34,
            color=theme.tokens["primary"],
            background=self.winfo_toplevel().cget("background"),
            theme=theme,
        ).pack(
            side="left", padx=(0, 14)
        )
        names = Surface(detail_header, role="background", theme=theme)
        names.pack(side="left", fill="x", expand=True)
        self.name_label = Label(names, variant="title", theme=theme)
        self.name_label.pack(anchor="w")
        self.enabled_badge = Badge(names, text=self.t("Enabled"), variant="primary", theme=theme)
        self.disabled_badge = Badge(names, text=self.t("Disabled"), variant="secondary", theme=theme)
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

        Surface(self.detail_card, role="background", padding=4, theme=theme).pack(fill="x")
        self.summary_label = Label(
            self.detail_card,
            text=self.t("Plugin details"),
            variant="section",
            theme=theme,
        )
        self.version_label = Label(self.detail_card, theme=theme)
        self.id_label = Label(self.detail_card, variant="muted", theme=theme)
        self.source_label = Label(self.detail_card, theme=theme)
        self.runtime_label = Label(self.detail_card, theme=theme)
        self.data_label = Label(self.detail_card, variant="muted", theme=theme, wraplength=700)
        self.capabilities_label = Label(self.detail_card, variant="muted", theme=theme, wraplength=700)
        self.summary_label.pack(anchor="w", pady=(8, 12))
        for detail_label in (self.version_label, self.source_label, self.runtime_label):
            detail_label.pack(anchor="w", pady=(0, 8))
        self.access_label = Label(
            self.detail_card,
            text=self.t("Data and permissions"),
            variant="section",
            theme=theme,
        )
        self.access_label.pack(anchor="w", pady=(16, 10))
        for detail_label in (self.id_label, self.data_label, self.capabilities_label):
            detail_label.pack(anchor="w", pady=(0, 7))
        self.disable_hint = Label(
            self.detail_card,
            text=self.t("Disabling removes this plugin from home, the sidebar, and search."),
            variant="muted",
            theme=theme,
            wraplength=700,
        )
        self.action_separator = Separator(self.detail_card, theme=theme)
        self.danger_label = Label(
            self.detail_card, text=self.t("Danger zone"), variant="section", theme=theme
        )
        self.uninstall_button = Button(
            self.detail_card,
            text=self.t("Uninstall"),
            command=lambda: on_manage("uninstall"),
            theme=theme,
            variant="outline",
            icon="trash",
        )
        self.delete_button = Button(
            self.detail_card,
            text=self.t("Delete saved data"),
            command=lambda: on_manage("delete"),
            theme=theme,
            variant="destructive",
            icon="trash",
        )
        self._show_empty()

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
        for detail_label in (self.version_label, self.source_label, self.runtime_label):
            detail_label.pack(anchor="w", pady=(0, 8))
        self.access_label.pack(anchor="w", pady=(16, 10))
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
        self.danger_label.pack(anchor="w", pady=(0, 8))
        self.uninstall_button.pack(side="right", padx=(8, 0))
        self.delete_button.pack(side="right")

    def set_records(self, records: list[dict[str, Any]] | tuple[dict[str, Any], ...]):
        self._all_records = tuple(records)
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


class SettingsView(Frame):
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
        header.pack(fill="x", padx=28, pady=(24, 18))
        body = Surface(self, role="background", theme=theme)
        body.pack(fill="both", expand=True, padx=28, pady=20)
        nav = Sidebar(body, theme=theme, width=220, padding=12)
        nav.pack(side="left", fill="y", padx=(0, 14))
        nav.pack_propagate(False)
        self.nav_buttons = {}
        NavigationItem(
            nav,
            text=self.t("Home"),
            command=on_home,
            theme=theme,
            icon="home",
        ).pack(fill="x", pady=(0, 8))
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
        viewport = ScrollArea(body, theme=theme, resize_debounce_ms=60)
        viewport.pack(side="left", fill="both", expand=True)
        self.content = viewport.content
        self.content.configure(padding=(0, 0, 8, 8))
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
            row, textvariable=self.language_var, state="readonly", width=24, theme=theme
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
            row, textvariable=self.mode_var, state="readonly", width=24, theme=theme
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
        Separator(about, theme=theme).pack(fill="x")
        Label(about, text=self.t("License: MIT"), theme=theme).pack(anchor="w", pady=(14, 4))
        Label(
            about,
            text=self.t("Third-party notices are included with the application."),
            variant="muted",
            theme=theme,
        ).pack(anchor="w")

        self.configure_options(language_preference, mode_preference)
        self.show_section("general")

    def _section(self, identifier, title, subtitle):
        frame = Card(self.content, theme=self.theme, padding=24)
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
