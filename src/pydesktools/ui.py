"""Application-owned views composed exclusively from PyDeskUI primitives."""

import tkinter as tk
from typing import Literal

from pydeskui import (
    Badge,
    Button,
    Card,
    DetailView,
    FieldSpec,
    Form,
    Frame,
    Item,
    ItemList,
    Label,
    SearchEntry,
    Select,
    Separator,
    SplitPane,
    Toolbar,
)


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


class JSONToolView(Frame):
    """Business layout for command input, execution, and result actions."""

    def __init__(self, master, *, fields, translate, on_search, on_select, on_command, theme):
        super().__init__(master, theme=theme)
        self.t = translate
        self.search = SearchEntry(self, on_change=on_search, theme=theme)
        self.search.pack(fill="x", pady=(4, 8))
        self.tool_list = ItemList(self, theme=theme, on_select=on_select)
        self.tool_list.tree.configure(height=2)
        self.tool_list.pack(fill="x")

        self.input_card = Card(self, theme=theme)
        self.input_card.pack(fill="both", expand=True, pady=(10, 5))
        self.form = Form(self.input_card, fields=fields, theme=theme)
        self.form.pack(fill="both", expand=True)
        self.input_actions = Toolbar(self.input_card, theme=theme)
        self.input_actions.pack(fill="x", pady=(8, 0))

        self.buttons = {}
        for title, command, variant in (
            ("Format", "format", "primary"),
            ("Minify", "minify", "secondary"),
            ("Import", "import", "default"),
        ):
            button = Button(
                self.input_actions,
                text=self.t(title),
                command=lambda value=command: on_command(value),
                theme=theme,
                variant=variant,
            )
            button.pack(side="left", padx=(0, 8))
            self.buttons[command] = button

        self.result_card = Card(self, theme=theme)
        self.result_card.pack(fill="both", expand=True, pady=(5, 4))
        self.result_actions = Toolbar(self.result_card, theme=theme)
        self.result_actions.pack(fill="x", pady=(0, 8))
        for title, command in (("Export", "export"), ("Copy", "copy")):
            button = Button(
                self.result_actions,
                text=self.t(title),
                command=lambda value=command: on_command(value),
                theme=theme,
                variant="secondary" if command == "copy" else "default",
            )
            button.pack(side="right", padx=(8, 0))
            self.buttons[command] = button
        self.detail = DetailView(self.result_card, theme=theme)
        self.detail.text.configure(height=7)
        self.detail.pack(fill="both", expand=True)
        self.detail.set_content(self.t("JSON result"), self.t("No result yet"))

    @property
    def command_buttons(self):
        return [self.buttons[name] for name in ("format", "minify", "import", "copy", "export")]

    def replace_form(self, fields, values=None):
        self.form.destroy()
        self.form = Form(self.input_card, fields=fields, theme=self.theme)
        self.form.pack(fill="both", expand=True, before=self.input_actions)
        if values:
            self.form.set_values(values)

    def show_command_context(self, *, json_tools, run_title=None):
        for command in ("minify", "import"):
            if json_tools:
                self.buttons[command].pack(side="left", padx=(0, 8))
            else:
                self.buttons[command].pack_forget()
        if json_tools:
            self.result_actions.pack(fill="x", pady=(0, 8))
        else:
            self.result_actions.pack_forget()
        self.buttons["format"].configure(
            text=self.t("Format") if json_tools else (run_title or self.t("Run"))
        )


class PluginManagerView(Frame):
    """Installed-plugin master/detail view with actions beside their target."""

    def __init__(
        self,
        master,
        *,
        translate,
        on_install,
        on_restore,
        on_manage,
        theme,
        bundled_plugin_id,
    ):
        super().__init__(master, theme=theme)
        self.t = translate
        self.bundled_plugin_id = bundled_plugin_id
        self.records = {}

        top = Toolbar(self, theme=theme)
        top.pack(fill="x", pady=(4, 10))
        self.install_button = Button(
            top, text=self.t("Install local bundle"), command=on_install, theme=theme
        )
        self.install_button.pack(side="left")
        self.restore_button = Button(
            top,
            text=self.t("Restore JSON tool"),
            command=on_restore,
            theme=theme,
            variant="secondary",
        )

        self.split = SplitPane(self, orient="horizontal", theme=theme)
        self.split.pack(fill="both", expand=True)
        list_card = Card(self.split, theme=theme)
        self.plugin_list = ItemList(list_card, theme=theme, on_select=self._selected)
        self.plugin_list.pack(fill="both", expand=True)
        self.detail_card = Card(self.split, theme=theme)
        self.split.add(list_card, weight=1)
        self.split.add(self.detail_card, weight=2)

        self.name_label = Label(self.detail_card, theme=theme)
        self.name_label.pack(anchor="w")
        self.enabled_badge = Badge(
            self.detail_card, text=self.t("Enabled"), variant="primary", theme=theme
        )
        self.disabled_badge = Badge(
            self.detail_card, text=self.t("Disabled"), variant="secondary", theme=theme
        )
        self.version_label = Label(self.detail_card, theme=theme)
        self.id_label = Label(self.detail_card, theme=theme)
        self.version_label.pack(anchor="w", pady=(12, 2))
        self.id_label.pack(anchor="w", pady=(0, 12))

        self.action_separator = Separator(self.detail_card, theme=theme)
        self.action_separator.pack(fill="x", pady=(4, 10))
        self.enable_button = Button(
            self.detail_card,
            text=self.t("Enable"),
            command=lambda: on_manage("enable"),
            theme=theme,
            variant="primary",
        )
        self.disable_button = Button(
            self.detail_card,
            text=self.t("Disable"),
            command=lambda: on_manage("disable"),
            theme=theme,
            variant="secondary",
        )
        self.uninstall_button = Button(
            self.detail_card,
            text=self.t("Uninstall"),
            command=lambda: on_manage("uninstall"),
            theme=theme,
            variant="destructive",
        )
        self.delete_button = Button(
            self.detail_card,
            text=self.t("Delete saved data"),
            command=lambda: on_manage("delete"),
            theme=theme,
            variant="destructive",
        )
        for button in (
            self.enable_button,
            self.disable_button,
            self.uninstall_button,
            self.delete_button,
        ):
            button.pack(anchor="w", pady=(0, 8))
        self._show_empty()

    def _show_empty(self):
        self.name_label.configure(text=self.t("Select a plugin"))
        self.version_label.configure(text="")
        self.id_label.configure(text="")
        for widget in (
            self.enabled_badge,
            self.disabled_badge,
            self.action_separator,
            self.enable_button,
            self.disable_button,
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
        self.version_label.configure(text=f'{self.t("Version")}: {manifest["version"]}')
        self.id_label.configure(text=f'{self.t("Plugin ID")}: {record["id"]}')
        self.enabled_badge.pack_forget()
        self.disabled_badge.pack_forget()
        (self.enabled_badge if record["enabled"] else self.disabled_badge).pack(
            anchor="w", pady=(8, 0)
        )
        self.action_separator.pack(fill="x", pady=(12, 10))
        self.enable_button.pack_forget()
        self.disable_button.pack_forget()
        (self.disable_button if record["enabled"] else self.enable_button).pack(
            anchor="w", pady=(0, 8)
        )
        self.uninstall_button.pack(anchor="w", pady=(0, 8))
        self.delete_button.pack(anchor="w", pady=(0, 8))

    def set_records(self, records):
        selected = self.plugin_list.selected_id()
        records = tuple(records)
        self.records = {record["id"]: record for record in records}
        self.plugin_list.set_items(
            [
                Item(
                    record["id"],
                    record["manifest"]["name"],
                    (self.t("Enabled") if record["enabled"] else self.t("Disabled"))
                    + " · "
                    + record["manifest"]["version"],
                )
                for record in records
            ]
        )
        ids = tuple(self.records)
        target = selected if selected in self.records else (ids[0] if ids else None)
        if target:
            self.plugin_list.tree.selection_set(target)
            self.plugin_list.tree.see(target)
            self._selected(target)
        else:
            self._show_empty()
        if self.bundled_plugin_id in self.records:
            self.restore_button.pack_forget()
        else:
            self.restore_button.pack(side="left", padx=(8, 0))

    def selected_id(self):
        return self.plugin_list.selected_id()

    def set_busy(self, busy):
        state = ["disabled"] if busy else ["!disabled"]
        self.install_button.state(state)
        self.plugin_list.tree.state(state)
        for button in (
            self.restore_button,
            self.enable_button,
            self.disable_button,
            self.uninstall_button,
            self.delete_button,
        ):
            button.state(state)


class SettingsView(Frame):
    """Application preferences with display labels separate from stored IDs."""

    LANGUAGE_IDS = ("system", "en", "zh-CN")
    MODE_IDS = ("system", "light", "dark")

    def __init__(
        self,
        master,
        *,
        translate,
        language_preference,
        mode_preference,
        on_language,
        on_mode,
        theme,
    ):
        super().__init__(master, theme=theme)
        self.t = translate
        self.language_var = tk.StringVar(master=self)
        self.mode_var = tk.StringVar(master=self)

        language_card = Card(self, theme=theme)
        language_card.pack(fill="x", pady=(12, 6))
        self.language_label = Label(language_card, text=self.t("Language"), theme=theme)
        self.language_label.pack(anchor="w", pady=(0, 6))
        self.language_select = Select(
            language_card,
            textvariable=self.language_var,
            state="readonly",
            width=28,
            theme=theme,
        )
        self.language_select.pack(anchor="w")
        self.language_select.bind("<<ComboboxSelected>>", lambda event: on_language())

        mode_card = Card(self, theme=theme)
        mode_card.pack(fill="x", pady=6)
        self.mode_label = Label(mode_card, text=self.t("Appearance"), theme=theme)
        self.mode_label.pack(anchor="w", pady=(0, 6))
        self.mode_select = Select(
            mode_card,
            textvariable=self.mode_var,
            state="readonly",
            width=28,
            theme=theme,
        )
        self.mode_select.pack(anchor="w")
        self.mode_select.bind("<<ComboboxSelected>>", lambda event: on_mode())
        self.configure_options(language_preference, mode_preference)

    def configure_options(self, language_preference, mode_preference):
        self._language_labels = (self.t("Follow system"), "English", "简体中文")
        self._mode_labels = (
            self.t("Follow system"),
            self.t("Light"),
            self.t("Dark"),
        )
        self.language_select.configure(values=self._language_labels)
        self.mode_select.configure(values=self._mode_labels)
        language_index = self.LANGUAGE_IDS.index(language_preference)
        mode_index = self.MODE_IDS.index(mode_preference)
        self.language_var.set(self._language_labels[language_index])
        self.mode_var.set(self._mode_labels[mode_index])

    def language_preference(self):
        return self.LANGUAGE_IDS[self._language_labels.index(self.language_var.get())]

    def mode_preference(self):
        return self.MODE_IDS[self._mode_labels.index(self.mode_var.get())]

    def set_language_preference(self, preference):
        self.language_var.set(self._language_labels[self.LANGUAGE_IDS.index(preference)])

    def set_mode_preference(self, preference):
        self.mode_var.set(self._mode_labels[self.MODE_IDS.index(preference)])
