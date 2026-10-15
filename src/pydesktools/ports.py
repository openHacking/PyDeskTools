"""Host-owned port manager view; operating-system operations stay in the worker."""

import tkinter as tk
from tkinter import ttk

from pydeskui import (
    Button,
    Card,
    DetailView,
    Frame,
    Label,
    Popover,
    SearchEntry,
    SegmentedControl,
    Table,
    Toolbar,
)


class PortManagerView(Frame):
    COLUMNS = ("ports", "project", "process", "pid", "uptime")
    HEADINGS = ("Ports", "Project", "Process", "PID", "Uptime")

    def __init__(self, master, *, translate, on_scan, on_stop, theme):
        super().__init__(master, theme=theme, padding=24)
        self.t, self.on_stop = translate, on_stop
        self.services = {}
        self.busy = False
        self.selected = None
        self.scanned = False
        self.sort_column, self.sort_direction = "ports", "ascending"
        self._rows = []
        self._column_widths = {}

        header = Frame(self, theme=theme)
        header.pack(fill="x", pady=(0, 20))
        title = Frame(header, theme=theme)
        title.pack(side="left", fill="x", expand=True)
        Label(title, text=self.t("Port Manager"), variant="title", theme=theme).pack(anchor="w")
        Label(title, text=self.t("Find the project using a port, then stop its service."),
              variant="muted", theme=theme).pack(anchor="w", pady=(6, 0))
        self.scope_button = Button(header, text=self.t("Scan scope"), variant="ghost", theme=theme,
                                   command=self.show_scope)
        self.scope_button.pack(side="right")
        self.scope = Popover(self.scope_button, theme=theme)
        Label(self.scope.content, text=self.t("Scan scope"), variant="section", theme=theme).pack(
            anchor="w", pady=(0, 8))
        self.warning = Label(self.scope.content, text=self.t(
            "Local machine only. Permissions may hide listeners or process details; "
            "Docker, WSL and remote services are not inspected internally."),
            wraplength=380, justify="left", variant="muted", theme=theme)
        self.warning.pack(fill="x")
        self.scope_done = Button(self.scope.content, text=self.t("Done"), variant="ghost",
                                 command=self.scope.hide, theme=theme)
        self.scope_done.pack(anchor="e", pady=(12, 0))

        controls = Toolbar(self, theme=theme)
        controls.pack(fill="x", pady=(0, 12))
        self.scan_button = Button(controls, text=self.t("Scan ports"), command=on_scan,
                                  theme=theme)
        self.scan_button.pack(side="right", padx=(12, 0))
        self.search = SearchEntry(controls, placeholder=self.t("Search port, project or process"),
                                  on_change=lambda value: self.render(), debounce_ms=0, theme=theme)
        self.search.pack(side="left", fill="x", expand=True)
        filters = Toolbar(self, theme=theme)
        filters.pack(fill="x", pady=(0, 12))
        self.filter_var = tk.StringVar(master=self, value="development")
        self.filter_control = SegmentedControl(
            filters, values=(("development", self.t("Development hints")),
                             ("all", self.t("All listeners"))),
            variable=self.filter_var, command=self.render, theme=theme)
        self.filter_control.pack(side="left")
        self.count = Label(filters, text="", variant="muted", theme=theme)
        self.count.pack(side="right")
        self.status = Label(self, text="", theme=theme, wraplength=800, justify="left")

        self.table_host = Frame(self, theme=theme)
        self.table_host.pack(fill="both", expand=True)
        self.table_host.columnconfigure(0, weight=1)
        self.table_host.rowconfigure(0, weight=1)
        self.table = Table(self.table_host, columns=self.COLUMNS, selectmode="browse", height=6,
                           on_sort=self.sort, theme=theme)
        self.table.grid(row=0, column=0, sticky="nsew")
        for column, heading in zip(self.COLUMNS, self.HEADINGS):
            self.table.heading(column, text=self.t(heading), anchor="w")
            self.table.column(column, width=120, minwidth=80, stretch=False, anchor="w")
        # Table exposes standard scrolling APIs; the themed native scrollbars keep
        # every column accessible when its content exceeds the viewport width.
        self.horizontal = ttk.Scrollbar(self.table_host, orient="horizontal",
                                        command=self.table.xview,
                                        style=theme.name("Horizontal.TScrollbar"))
        self.horizontal.grid(row=1, column=0, sticky="ew")
        self.vertical = ttk.Scrollbar(self.table_host, orient="vertical", command=self.table.yview,
                                      style=theme.name("Vertical.TScrollbar"))
        self.vertical.grid(row=0, column=1, sticky="ns")
        self.table.configure(xscrollcommand=self.scroll_x, yscrollcommand=self.scroll_y)
        self.table.bind("<<TreeviewSelect>>", self.table_selected, add="+")
        self.table.bind("<Configure>", self.resize_columns, add="+")
        self.empty = Label(self.table_host, text=self.t("Scan ports to inspect running services."),
                           variant="muted", theme=theme)
        self.empty.place(relx=0.5, rely=0.45, anchor="center")

        self.inspector = Card(self, padding=16, bordered=True, theme=theme)
        # Reserve the inspector before the expanding table, so a small window
        # gives the table scrollbars instead of starving the details of height.
        self.inspector.pack(side="bottom", fill="x", before=self.table_host, pady=(16, 0))
        selection_header = Toolbar(self.inspector, theme=theme)
        selection_header.pack(fill="x")
        self.selection_title = Label(selection_header, text=self.t("Service details"),
                                     variant="section", theme=theme)
        self.selection_title.pack(side="left", fill="x", expand=True)
        self.more_button = Button(selection_header, text=self.t("More actions"), variant="ghost",
                                  theme=theme, command=self.show_more)
        self.more_button.pack(side="right", padx=(8, 0))
        self.stop_button = Button(selection_header, text=self.t("Stop service"), variant="primary",
                                  command=lambda: self.request_stop(False), theme=theme)
        self.stop_button.pack(side="right")
        self.more = Popover(self.more_button, padding=12, theme=theme)
        self.force_button = Button(self.more.content, text=self.t("Force termination"),
                                   command=lambda: self.request_stop(True), theme=theme,
                                   variant="ghost")
        self.force_button.pack(fill="x")
        self.selection_meta = Label(self.inspector, text=self.t(
            "Select a row to see all listening addresses and the startup command."),
            variant="muted", theme=theme, wraplength=760, justify="left")
        self.selection_meta.pack(fill="x", pady=(8, 0))
        self.detail = DetailView(self.inspector, theme=theme)
        self.detail.title.grid_remove()
        self.detail.text.configure(height=6)
        self.detail.pack(fill="x", pady=(8, 0))
        self.detail.pack_forget()
        self.bind("<Configure>", self.resize_text, add="+")
        self.render()
        self.set_busy(False)

    def _refresh_theme(self):
        # Re-measure cells when the shared system font or UI density changes.
        if hasattr(self, "table") and hasattr(self, "_rows"):
            self.fit_columns()

    def show_scope(self):
        self.scope.toggle(anchor=self.scope_button, focus=self.scope_done)

    def show_more(self):
        if self.selected and self.selected["can_stop"] and not self.busy:
            self.more.toggle(anchor=self.more_button, focus=self.force_button)

    def resize_text(self, event):
        self.status.configure(wraplength=max(180, event.width - 48))
        self.selection_meta.configure(wraplength=max(180, event.width - 80))

    def scroll_x(self, first, last):
        self.horizontal.set(first, last)
        if float(first) <= 0 and float(last) >= 1:
            self.horizontal.grid_remove()
        else:
            self.horizontal.grid()

    def scroll_y(self, first, last):
        self.vertical.set(first, last)
        if float(first) <= 0 and float(last) >= 1:
            self.vertical.grid_remove()
        else:
            self.vertical.grid()

    @staticmethod
    def endpoint(endpoint):
        address = endpoint["address"]
        if ":" in address and not address.startswith("["):
            address = f"[{address}]"
        return f"{address}:{endpoint['port']}"

    @classmethod
    def endpoints(cls, service):
        return ", ".join(cls.endpoint(e) for e in service["endpoints"])

    def uptime(self, seconds):
        minutes = seconds // 60
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        if days:
            return self.t("{days}d {hours}h").format(days=days, hours=hours)
        if hours:
            return self.t("{hours}h {minutes}m").format(hours=hours, minutes=minutes)
        return self.t("{minutes}m").format(minutes=minutes)

    def values(self, service):
        ports = ", ".join(map(str, sorted({e["port"] for e in service["endpoints"]})))
        return (ports, service["project"] or self.t("Unknown project"),
                service["name"] or self.t("Unavailable"), service["pid"],
                self.uptime(service["age_seconds"]))

    def fit_columns(self):
        minimums = (110, 170, 100, 80, 100)
        widths = {}
        for index, column in enumerate(self.COLUMNS):
            # Measure the actual strings, including long project names and all ports.
            # Full values remain in cells; overflow is scrollable, never silently lost.
            values = [str(self.values(service)[index]) for service in self._rows]
            widths[column] = max(self.theme.px(minimums[index]),
                                 self.theme.font.measure(self.t(self.HEADINGS[index])) + 36,
                                 max((self.theme.font.measure(v) + 36 for v in values), default=0))
        self._column_widths = widths
        self.resize_columns()

    def resize_columns(self, event=None):
        if not self._column_widths:
            return
        widths = dict(self._column_widths)
        viewport_width = event.width if event is not None else self.table.winfo_width()
        extra = max(0, viewport_width - 8 - sum(widths.values()))
        widths["project"] += extra
        for column, width in widths.items():
            self.table.column(column, width=width, minwidth=width, stretch=False)

    def sort(self, column, direction):
        self.sort_column, self.sort_direction = column, direction
        self.render()

    def set_status(self, text):
        self.status.configure(text=text)
        if text:
            self.status.pack(fill="x", before=self.table_host, pady=(0, 12))
        else:
            self.status.pack_forget()

    def begin_operation(self, command):
        self.set_status(self.t("Scanning ports…" if command == "scan" else "Stopping service…"))

    def show_error(self, message):
        self.set_status(self.t("Error") + ": " + self.t(message))

    def set_result(self, data):
        self.scanned = True
        self.services = {str(service["pid"]): service for service in data["services"]}
        self.select(None)
        status = self.t(data["status"]) if data["status"] else ""
        for key, label in (("released_ports", "No observed listeners on ports"),
                           ("occupied_ports", "Listeners remain on original port numbers")):
            if data.get(key):
                status += "\n" + self.t(label) + ": " + ", ".join(map(str, data[key]))
        self.set_status(status.strip())
        self.warning.configure(text="\n".join(self.t(w) for w in data["warnings"]))
        self.render()

    def render(self):
        query = self.search.get().casefold().strip()
        services = [s for s in self.services.values()
                    if (self.filter_var.get() == "all" or s["development"])
                    and query in (self.endpoints(s) + " " + s["project"] + " " + s["name"]
                                  + " " + s["cwd"] + " " + s["command"] + " " + str(s["pid"])).casefold()]
        def sort_key(service):
            if self.sort_column == "ports":
                return tuple(sorted({e["port"] for e in service["endpoints"]}))
            if self.sort_column == "pid":
                return service["pid"]
            if self.sort_column == "uptime":
                return service["age_seconds"]
            return service["project" if self.sort_column == "project" else "name"].casefold()
        self._rows = sorted(services, key=sort_key, reverse=self.sort_direction == "descending")
        # Keep the inspector in sync with the actual visible selection. Filtering
        # or replacing a scan removes a hidden/stale selection and its actions.
        selected_id = str(self.selected["pid"]) if self.selected else None
        self.table.delete(*self.table.get_children())
        for service in self._rows:
            self.table.insert("", "end", iid=str(service["pid"]), values=self.values(service))
        if selected_id and self.table.exists(selected_id):
            self.table.selection_set(selected_id)
            self.table.focus(selected_id)
            self.select(selected_id)
        else:
            self.select(None)
        if self._rows:
            self.empty.place_forget()
        else:
            empty_text = "Scan ports to inspect running services."
            if self.scanned:
                empty_text = ("No matching listeners." if self.services else
                              "No listeners found. Try scanning again or showing all listeners.")
            self.empty.configure(text=self.t(empty_text))
            self.empty.place(relx=0.5, rely=0.45, anchor="center")
        self.count.configure(text=self.t("{services} services · {ports} ports").format(
            services=len(self._rows), ports=len({e["port"] for s in self._rows for e in s["endpoints"]})))
        self.fit_columns()
        self.set_busy(self.busy)

    def table_selected(self, event=None):
        selection = self.table.selection()
        self.select(selection[0] if selection else None)

    def select(self, identifier):
        self.selected = self.services.get(identifier)
        self.more.hide()
        if self.selected:
            s = self.selected
            self.selection_title.configure(text=self.t("Selected service"))
            self.selection_meta.configure(text=f"{s['project'] or self.t('Unknown project')}  ·  "
                                          f"{s['name']}  ·  PID {s['pid']}  ·  {s['username']}")
            body = (self.t("Listening addresses") + "\n"
                    + "\n".join(self.endpoint(e) for e in s["endpoints"])
                    + "\n" + self.t("Project directory") + ": " + (s["cwd"] or self.t("Unavailable"))
                    + "\n" + self.t("Startup command") + ": " + (s["command"] or self.t("Unavailable")))
            if not s["can_stop"]:
                body += "\n\n" + self.t("This process cannot be stopped by this tool")
            self.detail.set_content("", body)
            self.detail.pack(fill="x", pady=(8, 0))
        else:
            self.selection_title.configure(text=self.t("Service details"))
            self.selection_meta.configure(text=self.t(
                "Select a row to see all listening addresses and the startup command."))
            self.detail.set_content("", "")
            self.detail.pack_forget()
        self.set_busy(self.busy)

    def set_busy(self, busy):
        self.busy = busy
        self.scan_button.state(["disabled"] if busy else ["!disabled"])
        usable = self.selected and self.selected["can_stop"] and not busy
        for button in (self.stop_button, self.more_button, self.force_button):
            button.state(["!disabled"] if usable else ["disabled"])
        if busy:
            self.more.hide()

    def request_stop(self, force):
        if self.selected and self.selected["can_stop"] and not self.busy:
            self.more.hide()
            self.on_stop(dict(self.selected), force)
