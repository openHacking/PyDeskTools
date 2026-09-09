"""Opt-in packaged installation diagnostic, using a disposable profile."""

import sys
import threading
import time
from importlib.resources import files
from pathlib import Path

PLUGIN = "org.pydesk.json-tools"
IMAGE_PLUGIN = "org.pydesk.image-compressor"


def start(app, destination, started):
    def ready():
        if app.background_busy:
            app.scheduler.call_later(50, ready)
            return

        gui_tk_version = str(app.root.tk.call("package", "provide", "Tk"))

        def verify():
            report = {
                "frozen": bool(getattr(sys, "frozen", False)),
                "gui_tk_version": gui_tk_version,
                "tkdnd_version": app.dnd_version,
                "startup_seconds": round(time.monotonic() - started, 3),
            }
            try:
                services = app.services
                image_record = services.store.get(IMAGE_PLUGIN)
                assert image_record and image_record["enabled"]
                assert int(gui_tk_version.split(".")[0]) >= 9
                if report["frozen"]:
                    assert app.dnd_available and app.dnd_version
                report["plugin_versions"] = {
                    IMAGE_PLUGIN: image_record["manifest"]["version"],
                    PLUGIN: services.store.get(PLUGIN)["manifest"]["version"],
                }
                from PIL import Image
                with Image.open(Path(__file__).parent / "assets/logo.png") as logo:
                    pixel = logo.getpixel((0, 0))
                    assert isinstance(pixel, tuple) and len(pixel) == 4 and pixel[3] == 0
                report["transparent_icon"] = True
                source = services.store.root / "verification-image.png"
                broken = services.store.root / "verification-broken.png"
                Image.new("RGB", (96, 64), "#336699").save(source)
                broken.write_bytes(b"not an image")
                image_result = services.commands.submit(
                    IMAGE_PLUGIN, "compress",
                    {"paths": [str(broken), str(source)], "format": "webp", "keep_larger": True},
                ).result(15)
                assert [item["status"] for item in image_result["data"]["items"]] == ["failed", "completed"]
                assert Path(image_result["data"]["items"][1]["output"]).is_file()
                report["image_batch_partial_failure"] = True
                assert {command["id"] for command in image_record["descriptor"]["commands"]} == {
                    "import_images",
                    "preview",
                    "compress",
                }
                first = services.commands.submit(
                    PLUGIN,
                    "format",
                    {"text": '{"number":12345678901234567890.123456789,"text":"世界"}'},
                )
                result = first.result(15)
                assert "12345678901234567890.123456789" in result["data"]["text"]
                worker = services._workers[PLUGIN]
                report["worker_executable"] = worker.process.args[0]
                report["runtime_executable"] = str(services.installer.python)
                report["worker_pid"] = worker.process.pid
                assert "pydesk_json_tools" not in sys.modules
                report["host_imported_plugin"] = False
                services.commands.submit(
                    PLUGIN, "copy", {"artifact_id": result["data"]["artifact_id"]}
                ).result(15)
                report["clipboard_expected"] = result["data"]["text"]
                large = services.import_text(PLUGIN, '{"text":"' + "世" * 30000 + '"}')
                output = services.commands.submit(PLUGIN, "minify", {"artifact_id": large}).result(
                    15
                )
                assert output["data"]["truncated"]
                assert len(output["view"]["body"].encode()) <= 65536
                report["large_result_bytes"] = output["data"]["bytes"]
                services.disable(PLUGIN)
                assert worker.process.poll() is not None
                services.uninstall(PLUGIN)
                assert services.store.decision(PLUGIN) == "uninstalled"
                services.install(
                    Path(str(files("pydesktools").joinpath("bundles", "json-tools.pdtplugin"))),
                    consent=True,
                    official=True,
                )
                assert (
                    services.commands.submit(PLUGIN, "minify", {"text": "{}"}).result(15)["data"][
                        "text"
                    ]
                    == "{}"
                )
                image_worker = services._workers.get(IMAGE_PLUGIN)
                services.disable(IMAGE_PLUGIN)
                if image_worker:
                    assert image_worker.process.poll() is not None
                services.uninstall(IMAGE_PLUGIN)
                assert services.store.decision(IMAGE_PLUGIN) == "uninstalled"
                services.install(
                    Path(
                        str(files("pydesktools").joinpath("bundles", "image-compressor.pdtplugin"))
                    ),
                    consent=True,
                    official=True,
                )
                restored_image = services.store.get(IMAGE_PLUGIN)
                assert restored_image and restored_image["enabled"]
                report["passed"] = True
            except Exception as error:
                report["passed"] = False
                report["error"] = str(error)
            report["total_seconds"] = round(time.monotonic() - started, 3)
            app.events.put(
                {"type": "verification", "report": report, "destination": str(destination)}
            )

        threading.Thread(target=verify, daemon=True).start()

    ready()
