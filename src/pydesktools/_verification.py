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

        def verify():
            report = {
                "frozen": bool(getattr(sys, "frozen", False)),
                "startup_seconds": round(time.monotonic() - started, 3),
            }
            try:
                services = app.services
                image_record = services.store.get(IMAGE_PLUGIN)
                assert image_record and image_record["enabled"]
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
