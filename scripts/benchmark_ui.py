"""Measure warm Tk UI operations using an isolated disposable profile. Run from repo root."""

import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

from pydesktools.app import IMAGE_PLUGIN, ApplicationConfig, application_tokens, create_application

folder = Path(tempfile.mkdtemp(prefix="pydesk-ui-benchmark-")).resolve()
app = create_application(
    ApplicationConfig(data_dir=folder / "profile", python=Path(sys.executable))
)
errors = []
app.error = errors.append
app.root.report_callback_exception = lambda *args: errors.append(str(args))


def settle():
    start = time.monotonic()
    while time.monotonic() - start < 30:
        app.root.update()
        if (
            not app.task
            and not app.background_busy
            and not app.image_preview_pending
            and app.image_tool._preview_resize_job is None
        ):
            return
        time.sleep(0.002)
    raise RuntimeError(
        f"UI did not settle: task={app.task}, background={app.background_busy}, pending={app.image_preview_pending}, resize={app.image_tool._preview_resize_job}, errors={errors}"
    )


def measure(action, count=12):
    values = []
    for n in range(count):
        start = time.perf_counter()
        action(n)
        app.root.update()
        values.append((time.perf_counter() - start) * 1000)
    return {"median_ms": round(statistics.median(values), 2), "max_ms": round(max(values), 2)}


try:
    settle()
    app.navigate("tool", IMAGE_PLUGIN)
    paths = []
    for index in range(2):
        p = folder / f"image-{index}.png"
        Image.new("RGB", (1200, 900), "#245578").save(p)
        paths.append(str(p))
    app.image_tool.set_files(paths)
    settle()
    app.image_tool.queue.tree.selection_set(paths[1])
    app.image_tool.queue._changed()
    settle()

    def cached(n):
        app.image_tool.queue.tree.selection_set(paths[n % 2])
        app.image_tool.queue._changed()

    result = {
        "python": sys.version.split()[0],
        "tk": app.root.tk.call("package", "require", "Tk"),
        "cached_preview": measure(cached),
    }
    result["navigation"] = measure(
        lambda n: app.navigate("home" if n % 2 else "tool", IMAGE_PLUGIN)
    )
    result["theme"] = measure(
        lambda n: app.theme.configure(
            mode="dark" if n % 2 else "light",
            tokens=application_tokens("dark" if n % 2 else "light"),
        ),
        6,
    )
    result["resize"] = measure(lambda n: app.root.geometry("1100x720" if n % 2 else "1280x840"))
    result["errors"] = errors
    result["cache_entries"] = len(app.preview_cache)
    Path("dist/verification").mkdir(parents=True, exist_ok=True)
    Path("dist/verification/ui-performance.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
finally:
    app._close()
    app._shutdown_thread.join(15)
