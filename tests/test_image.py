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
        report_progress=lambda fraction, message: None,
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
