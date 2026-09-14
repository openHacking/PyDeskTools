import sys
import threading
from pathlib import Path
from types import ModuleType

from pydesktools.tray import LinuxTray


class FakeRoot:
    def __init__(self):
        self.callbacks = {}
        self.next_id = 0

    def after(self, _delay, callback):
        self.next_id += 1
        self.callbacks[self.next_id] = callback
        return self.next_id

    def after_cancel(self, identifier):
        self.callbacks.pop(identifier, None)


class FakeMenu:
    SEPARATOR = object()

    def __init__(self, *items):
        self.items = items


class FakeMenuItem:
    def __init__(self, text, action, default=False):
        self.text = text
        self.action = action
        self.default = default


class FakeIcon:
    def __init__(self, name, image, title, menu):
        self.name = name
        self.image = image
        self.title = title
        self.menu = menu
        self.visible = False
        self.stopped = threading.Event()

    def run(self, setup):
        setup(self)
        self.stopped.wait(timeout=2)

    def stop(self):
        self.stopped.set()


def test_linux_tray_dispatches_show_and_quit_on_tk_thread(monkeypatch):
    module = ModuleType("pystray")
    module.Icon = FakeIcon
    module.Menu = FakeMenu
    module.MenuItem = FakeMenuItem
    monkeypatch.setitem(sys.modules, "pystray", module)
    root = FakeRoot()
    calls = []

    tray = LinuxTray(
        root,
        "PyDeskTools",
        Path(__file__).parents[1] / "src/pydesktools/assets/logo.png",
        lambda: calls.append("show"),
        lambda: calls.append("quit"),
    )
    try:
        assert tray.available
        assert tray._icon.visible
        show, _separator, quit_item = tray._icon.menu.items
        assert show.default
        show.action(tray._icon, show)
        quit_item.action(tray._icon, quit_item)

        tray._poll()

        assert calls == ["show", "quit"]
    finally:
        tray.close()
