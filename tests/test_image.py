from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from pydesk_image_compressor import ImageCompressor, _destination
from pydesktools_sdk import CancellationToken
from pydesktools_sdk.protocol import validate_view


class Host:
    def __init__(self, selected, output, artifact_root):
        self.selected = selected
        self.output = output
        self.artifact_root = artifact_root
        self.artifacts = {}

    def call(self, capability, **arguments):
        if capability == "dialogs.open_files":
            return [str(path) for path in self.selected]
        if capability == "dialogs.choose_directory":
            return str(self.output)
        if capability == "artifacts.import":
            source = self.artifact_root / arguments["relative_path"]
            identifier = source.stem
            destination = self.output / (identifier + ".png")
            destination.write_bytes(source.read_bytes())
            self.artifacts[identifier] = destination
            return identifier
        if capability == "artifacts.size":
            return self.artifacts[arguments["artifact_id"]].stat().st_size
        raise AssertionError(capability)


def context(tmp_path, selected):
    export = tmp_path / "cache"
    output = tmp_path / "output"
    output.mkdir()
    host = Host(selected, output, export / "export")
    plugin_context = SimpleNamespace(cache_dir=export, host=host)
    invocation = SimpleNamespace(
        cancellation=CancellationToken(),
        host=host,
        report_progress=lambda fraction, message, data=None: None,
    )
    return plugin_context, invocation, output


def options(**overrides):
    return {
        "format": "webp",
        "quality": 72,
        "max_width": None,
        "max_height": None,
        "preserve_metadata": False,
        "jpeg_background": None,
        "keep_larger": True,
        **overrides,
    }


def test_import_preview_and_compress_without_overwriting(tmp_path):
    source = tmp_path / "photo.png"
    Image.new("RGB", (320, 200), "#336699").save(source)
    original = source.read_bytes()
    plugin_context, invocation, output = context(tmp_path, [source])
    plugin = ImageCompressor()
    plugin.activate(plugin_context)

    imported = plugin.invoke("import_images", {}, invocation).data["files"]
    assert imported[0]["name"] == "photo.png"
    assert imported[0]["width"] == 320

    preview = plugin.invoke("preview", {"path": str(source), **options()}, invocation)
    assert preview.view["type"] == "image_compare"
    assert preview.data["estimated_bytes"] > 0

    result = plugin.invoke(
        "compress",
        {"paths": [str(source)], "output_directory": str(output), **options()},
        invocation,
    ).data
    assert not result["canceled"]
    destination = Path(result["items"][0]["output"])
    assert destination.name == "photo-compressed.webp"
    assert destination.exists()
    assert source.read_bytes() == original


def test_import_explicit_paths_accepts_valid_files_and_reports_rejections(tmp_path):
    valid = tmp_path / "有效 image.png"
    broken = tmp_path / "broken.webp"
    folder = tmp_path / "folder.jpg"
    Image.new("RGB", (64, 48), "#336699").save(valid)
    broken.write_bytes(b"not an image")
    folder.mkdir()
    plugin_context, invocation, _ = context(tmp_path, [])
    plugin = ImageCompressor()
    plugin.activate(plugin_context)

    result = plugin.invoke(
        "import_images",
        {"paths": [str(valid), str(broken), str(folder), str(valid)]},
        invocation,
    ).data

    assert [item["path"] for item in result["files"]] == [str(valid.resolve())]
    assert {Path(item["path"]).name for item in result["rejected"]} == {
        broken.name,
        folder.name,
    }
    assert all(item["message"] for item in result["rejected"])


def test_compress_without_output_directory_saves_beside_each_source(tmp_path):
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first = first_dir / "one.png"
    second = second_dir / "two.png"
    Image.new("RGB", (80, 60), "#224466").save(first)
    Image.new("RGB", (80, 60), "#446688").save(second)
    plugin_context, invocation, _ = context(tmp_path, [first, second])
    plugin = ImageCompressor()
    plugin.activate(plugin_context)

    result = plugin.invoke(
        "compress", {"paths": [str(first), str(second)], **options()}, invocation
    ).data

    assert result["output_directory"] is None
    assert (first_dir / "one-compressed.webp").is_file()
    assert (second_dir / "two-compressed.webp").is_file()


def test_transparent_jpeg_uses_white_default_background_and_resizes(tmp_path):
    source = tmp_path / "alpha.png"
    Image.new("RGBA", (400, 200), (1, 2, 3, 64)).save(source)
    plugin_context, invocation, _ = context(tmp_path, [source])
    plugin = ImageCompressor()
    plugin.activate(plugin_context)
    result = plugin.invoke(
        "preview",
        {
            "path": str(source),
            **options(format="jpeg", max_width=100),
        },
        invocation,
    )
    assert (result.data["width"], result.data["height"]) == (100, 50)


def test_destination_never_overwrites(tmp_path):
    source = tmp_path / "photo.jpg"
    source.write_bytes(b"source")
    first = tmp_path / "photo-compressed.jpg"
    first.write_bytes(b"existing")
    assert _destination(tmp_path, source, ".jpg").name == "photo-compressed-2.jpg"


def test_image_compare_protocol_rejects_paths_and_urls():
    view = {
        "type": "image_compare",
        "title": "Preview",
        "before_artifact_id": "before",
        "after_artifact_id": "after",
        "metadata": {"bytes": 10},
    }
    validate_view(view, {})
    with pytest.raises(ValueError):
        validate_view({**view, "url": "https://example.test/image.png"}, {})
    with pytest.raises(ValueError):
        validate_view({**view, "path": "/tmp/image.png"}, {})


def test_batch_failure_and_cancellation_preserve_completed_results(tmp_path):
    good = tmp_path / "good.png"
    Image.new("RGB", (128, 80), "red").save(good)
    bad = tmp_path / "broken.png"
    bad.write_bytes(b"not an image")
    plugin_context, invocation, _ = context(tmp_path, [])
    plugin = ImageCompressor()
    plugin.activate(plugin_context)
    result = plugin.invoke("compress", {"paths": [str(bad), str(good)], **options()}, invocation)
    assert [r["status"] for r in result.data["items"]] == ["failed", "completed"]
    assert Path(result.data["items"][1]["output"]).exists()
    def cancel_after_first(fraction, message, data=None):
        if data and data.get("items"):
            invocation.cancellation.cancel()
    invocation.report_progress = cancel_after_first
    result = plugin.invoke("compress", {"paths": [str(good), str(bad)], **options()}, invocation)
    assert result.data["canceled"]
    assert [r["status"] for r in result.data["items"]] == ["completed", "canceled"]
    assert Path(result.data["items"][0]["output"]).exists()
    assert not list(tmp_path.glob(".pydesk-*"))


def test_structured_progress_is_bounded():
    from pydesktools_sdk.protocol import validate_progress_data
    validate_progress_data(None)
    validate_progress_data({"items": [{"source": "a.png", "status": "completed"}]})
    for invalid in ([1], {"large": "x" * 524288}, {"number": float("nan")}):
        with pytest.raises(ValueError):
            validate_progress_data(invalid)


def test_latest_progress_checkpoint_is_delivered_during_long_work():
    import threading
    import time

    from pydesktools_sdk.runner import Worker
    worker = Worker.__new__(Worker)
    worker.progress_lock = threading.Lock()
    worker.progress_timer = None
    worker.pending_progress = None
    worker.last_progress = 0.0
    worker.task_id = "image-task"
    delivered = threading.Event()
    events = []
    def send(event):
        events.append(event)
        if len(events) == 2:
            delivered.set()
    worker.send = send
    worker.progress(0, "Starting", {"items": []})
    worker.progress(0.5, "Saved", {"items": [{"source": "first.png", "status": "completed"}]})
    assert delivered.wait(1)
    assert events[-1]["params"]["data"]["items"][0]["status"] == "completed"
    assert time.monotonic() - worker.last_progress < 1
