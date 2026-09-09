"""Capture a reproducible, data-free README hero from a local macOS desktop session."""

import tempfile
import time
from pathlib import Path

from PIL import ImageGrab

from pydesktools.app import ApplicationConfig, create_application

ROOT = Path(__file__).resolve().parents[1]


def settle(app):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        app.root.update()
        if not app.background_busy and not app.task:
            return
        time.sleep(0.01)
    raise RuntimeError("Application did not become idle before the README capture")


def main():
    profile = Path(tempfile.mkdtemp(prefix="pydesk-readme-")) / "profile"
    app = create_application(ApplicationConfig(data_dir=profile, display_name="PyDeskTools"))
    try:
        settle(app)
        app.settings.set_language_preference("en")
        app.change_language()
        settle(app)
        app.navigate("home")
        app.root.geometry("1120x720")
        app.root.update_idletasks()
        app.root.lift()
        app.root.update()
        time.sleep(1)
        app.root.update()
        x = app.root.winfo_rootx()
        y = app.root.winfo_rooty()
        width = app.root.winfo_width()
        height = app.root.winfo_height()
        image = ImageGrab.grab(bbox=(x, y, x + width, y + height))
        destination = ROOT / "docs/assets/pydesktools-home.png"
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination, optimize=True)
        print(destination)
    finally:
        app._close()
        app._shutdown_thread.join(15)


if __name__ == "__main__":
    main()
