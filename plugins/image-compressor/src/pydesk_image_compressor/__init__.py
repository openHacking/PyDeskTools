"""Offline image compression. Imported only by an isolated SDK worker."""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from pydesktools_sdk import CommandResult, PluginError

MAX_FILE_BYTES = 200 * 1024 * 1024
MAX_PIXELS = 40_000_000
SUPPORTED = {"JPEG", "PNG", "WEBP"}
FORMATS = {"jpeg": ("JPEG", ".jpg"), "png": ("PNG", ".png"), "webp": ("WEBP", ".webp")}

STR = {"type": "string"}
OPTIONS = {
    "format": {"type": "string", "enum": ["jpeg", "png", "webp"], "default": "jpeg"},
    "quality": {"type": "integer", "minimum": 1, "maximum": 100, "default": 80},
    "max_width": {"type": ["integer", "null"], "minimum": 1, "maximum": 32768},
    "max_height": {"type": ["integer", "null"], "minimum": 1, "maximum": 32768},
    "preserve_metadata": {"type": "boolean", "default": False},
    "jpeg_background": {"type": ["string", "null"]},
    "keep_larger": {"type": "boolean", "default": False},
}


def _input(properties, required=()):
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


FILE = _input(
    {
        "path": STR,
        "name": STR,
        "bytes": {"type": "integer"},
        "width": {"type": "integer"},
        "height": {"type": "integer"},
        "format": STR,
        "has_alpha": {"type": "boolean"},
    },
    ("path", "name", "bytes", "width", "height", "format", "has_alpha"),
)
IMPORT_OUTPUT = _input({"files": {"type": "array", "items": FILE, "maxItems": 1000}}, ("files",))
PREVIEW_OUTPUT = _input(
    {
        "before_artifact_id": STR,
        "after_artifact_id": STR,
        "original_bytes": {"type": "integer"},
        "estimated_bytes": {"type": "integer"},
        "width": {"type": "integer"},
        "height": {"type": "integer"},
    },
    (
        "before_artifact_id",
        "after_artifact_id",
        "original_bytes",
        "estimated_bytes",
        "width",
        "height",
    ),
)
RESULT_ITEM = _input(
    {
        "source": STR,
        "output": {"type": ["string", "null"]},
        "status": {"type": "string"},
        "original_bytes": {"type": "integer"},
        "output_bytes": {"type": ["integer", "null"]},
        "message": STR,
    },
    ("source", "output", "status", "original_bytes", "output_bytes", "message"),
)
COMPRESS_OUTPUT = _input(
    {
        "canceled": {"type": "boolean"},
        "output_directory": {"type": ["string", "null"]},
        "items": {"type": "array", "items": RESULT_ITEM, "maxItems": 1000},
    },
    ("canceled", "output_directory", "items"),
)


def _color(value):
    if not isinstance(value, str) or len(value) != 7 or not value.startswith("#"):
        raise PluginError("background_required", "Choose a background color for JPEG")
    try:
        return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))
    except ValueError:
        raise PluginError("background_required", "Choose a valid background color") from None


def _alpha(image):
    return image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)


def _open(path, cancellation):
    source = Path(path)
    try:
        if not source.is_file() or source.stat().st_size > MAX_FILE_BYTES:
            raise PluginError("invalid_image", "Image is missing or exceeds 200 MiB")
        cancellation.raise_if_cancelled()
        image = Image.open(source)
        if getattr(image, "n_frames", 1) != 1:
            image.close()
            raise PluginError("animated_image", "Animated images are not supported")
        if image.format not in SUPPORTED or image.width * image.height > MAX_PIXELS:
            image.close()
            raise PluginError("invalid_image", "Unsupported image or decoded image is too large")
        image.load()
        return source, image
    except PluginError:
        raise
    except (OSError, UnidentifiedImageError, ValueError):
        raise PluginError(
            "invalid_image", "The file is not a valid JPEG, PNG or WebP image"
        ) from None


def _prepared(image, options):
    result = ImageOps.exif_transpose(image)
    if result is image:
        result = image.copy()
    width = options.get("max_width") or result.width
    height = options.get("max_height") or result.height
    scale = min(1.0, width / result.width, height / result.height)
    if scale < 1:
        result = result.resize(
            (max(1, round(result.width * scale)), max(1, round(result.height * scale))),
            Image.Resampling.LANCZOS,
        )
    target = options.get("format", "jpeg")
    if target == "jpeg" and _alpha(result):
        background = Image.new(
            "RGB", result.size, _color(options.get("jpeg_background") or "#ffffff")
        )
        alpha = result.convert("RGBA")
        background.paste(alpha, mask=alpha.getchannel("A"))
        result.close()
        result = background
    elif target == "jpeg":
        converted = result.convert("RGB")
        result.close()
        result = converted
    return result


def _save(image, destination, source_image, options):
    target, _ = FORMATS[options.get("format", "jpeg")]
    kwargs = {}
    if target in ("JPEG", "WEBP"):
        kwargs["quality"] = options.get("quality", 80)
        kwargs["optimize"] = True
    elif target == "PNG":
        kwargs.update(optimize=True, compress_level=9)
    if options.get("preserve_metadata"):
        if source_image.info.get("icc_profile"):
            kwargs["icc_profile"] = source_image.info["icc_profile"]
        exif = source_image.getexif()
        exif.pop(274, None)
        if exif:
            kwargs["exif"] = exif.tobytes()
    image.save(destination, target, **kwargs)


def _destination(directory, source, extension):
    stem = source.stem + "-compressed"
    candidate = directory / (stem + extension)
    index = 2
    while candidate.exists() or candidate.resolve() == source.resolve():
        candidate = directory / f"{stem}-{index}{extension}"
        index += 1
    return candidate


class ImageCompressor:
    def activate(self, context):
        self.context = context
        self.export = context.cache_dir / "export"
        self.export.mkdir(parents=True, exist_ok=True)

    def describe(self):
        option_schema = dict(OPTIONS)
        return {
            "commands": [
                {
                    "id": "import_images",
                    "title": "Add images",
                    "description": "Choose JPEG, PNG or WebP images",
                    "effects": "read",
                    "retry": "manual",
                    "timeout_ms": 300000,
                    "input_schema": _input({}),
                    "output_schema": IMPORT_OUTPUT,
                },
                {
                    "id": "preview",
                    "title": "Preview compression",
                    "description": "Create a local before and after preview",
                    "effects": "pure",
                    "retry": "safe",
                    "timeout_ms": 300000,
                    "input_schema": _input({"path": STR, **option_schema}, ("path", "format")),
                    "output_schema": PREVIEW_OUTPUT,
                },
                {
                    "id": "compress",
                    "title": "Compress images",
                    "description": "Compress selected images beside their originals",
                    "effects": "write",
                    "retry": "manual",
                    "timeout_ms": 3600000,
                    "input_schema": _input(
                        {
                            "paths": {
                                "type": "array",
                                "items": STR,
                                "minItems": 1,
                                "maxItems": 1000,
                            },
                            "output_directory": {"type": ["string", "null"]},
                            **option_schema,
                        },
                        ("paths", "format"),
                    ),
                    "output_schema": COMPRESS_OUTPUT,
                },
            ]
        }

    def _artifact(self, image, source_image, options, *, processed):
        relative = uuid.uuid4().hex + ".png"
        path = self.export / relative
        preview = image.copy()
        preview.thumbnail((1200, 900), Image.Resampling.LANCZOS)
        encoded_size = None
        if processed:
            # Re-encode using selected settings, then normalize the comparison artifact to PNG.
            encoded = self.export / (uuid.uuid4().hex + FORMATS[options["format"]][1])
            try:
                _save(preview, encoded, source_image, options)
                encoded_size = encoded.stat().st_size
                with Image.open(encoded) as reopened:
                    reopened.load()
                    reopened.save(path, "PNG")
            finally:
                encoded.unlink(missing_ok=True)
        else:
            preview.save(path, "PNG")
        preview.close()
        try:
            identifier = self.context.host.call("artifacts.import", relative_path=relative)
            return identifier, encoded_size
        finally:
            path.unlink(missing_ok=True)

    def invoke(self, command_id, arguments, context):
        if command_id == "import_images":
            paths = context.host.call("dialogs.open_files", title="Add images") or []
            files = []
            for path in paths:
                source, image = _open(path, context.cancellation)
                try:
                    files.append(
                        {
                            "path": str(source),
                            "name": source.name,
                            "bytes": source.stat().st_size,
                            "width": image.width,
                            "height": image.height,
                            "format": image.format,
                            "has_alpha": _alpha(image),
                        }
                    )
                finally:
                    image.close()
            return CommandResult({"files": files})

        if command_id == "preview":
            source, image = _open(arguments["path"], context.cancellation)
            processed = _prepared(image, arguments)
            try:
                before_image = ImageOps.exif_transpose(image)
                before, _ = self._artifact(before_image, image, arguments, processed=False)
                if before_image is not image:
                    before_image.close()
                after, estimate = self._artifact(processed, image, arguments, processed=True)
                assert estimate is not None
                data = {
                    "before_artifact_id": before,
                    "after_artifact_id": after,
                    "original_bytes": source.stat().st_size,
                    "estimated_bytes": estimate,
                    "width": processed.width,
                    "height": processed.height,
                }
                return CommandResult(
                    data,
                    {
                        "type": "image_compare",
                        "title": "Compression preview",
                        **{key: data[key] for key in ("before_artifact_id", "after_artifact_id")},
                        "metadata": {
                            "original_bytes": data["original_bytes"],
                            "estimated_bytes": data["estimated_bytes"],
                            "width": data["width"],
                            "height": data["height"],
                        },
                    },
                )
            finally:
                processed.close()
                image.close()

        if command_id != "compress":
            raise PluginError("unknown_command", "Unknown image command")
        directory_value = arguments.get("output_directory")
        shared_directory = Path(directory_value) if directory_value else None
        if shared_directory is not None and not shared_directory.is_dir():
            raise PluginError("invalid_output", "Output folder does not exist")
        results = []
        paths = arguments["paths"]
        for index, path in enumerate(paths):
            context.cancellation.raise_if_cancelled()
            source, image = _open(path, context.cancellation)
            directory = shared_directory or source.parent
            processed = _prepared(image, arguments)
            extension = FORMATS[arguments.get("format", "jpeg")][1]
            destination = _destination(directory, source, extension)
            fd, temporary_name = tempfile.mkstemp(prefix=".pydesk-", dir=directory)
            os.close(fd)
            temporary = Path(temporary_name)
            try:
                _save(processed, temporary, image, arguments)
                with Image.open(temporary) as verification:
                    verification.verify()
                context.cancellation.raise_if_cancelled()
                output_bytes = temporary.stat().st_size
                if output_bytes >= source.stat().st_size and not arguments.get("keep_larger"):
                    results.append(
                        {
                            "source": str(source),
                            "output": None,
                            "status": "skipped_larger",
                            "original_bytes": source.stat().st_size,
                            "output_bytes": output_bytes,
                            "message": "Skipped because the compressed file would be larger",
                        }
                    )
                else:
                    os.replace(temporary, destination)
                    results.append(
                        {
                            "source": str(source),
                            "output": str(destination),
                            "status": "completed",
                            "original_bytes": source.stat().st_size,
                            "output_bytes": output_bytes,
                            "message": "Compressed",
                        }
                    )
            finally:
                temporary.unlink(missing_ok=True)
                processed.close()
                image.close()
            context.report_progress(
                (index + 1) / len(paths), f"Compressed {index + 1}/{len(paths)}"
            )
        return CommandResult(
            {
                "canceled": False,
                "output_directory": str(shared_directory) if shared_directory else None,
                "items": results,
            },
            {
                "type": "detail",
                "title": "Compression complete",
                "body": "\n".join(
                    f"{Path(item['source']).name}: {item['message']}" for item in results
                ),
            },
        )

    def deactivate(self):
        pass


def create_plugin():
    return ImageCompressor()
