"""Offline JSON tools. Imported only by the isolated SDK worker."""

import gettext
import sys
import uuid
from importlib.resources import files
from json import JSONDecoder
from pathlib import Path

import simplejson as json
from pydesktools_sdk import CommandResult, PluginError

scan_string = JSONDecoder().raw_decode

MAX_INPUT = 20 * 1024 * 1024
MAX_OUTPUT = 200 * 1024 * 1024
PREVIEW = 65536
INLINE = 32768

STR = {"type": "string"}
INPUT = {
    "type": "object",
    "properties": {
        "text": STR,
        "artifact_id": STR,
        "indent": {"type": "integer", "minimum": 0, "maximum": 8, "default": 2},
        "sort_keys": {"type": "boolean", "default": False},
    },
    "additionalProperties": False,
}
OUTPUT = {
    "type": "object",
    "properties": {
        "text": STR,
        "artifact_id": STR,
        "bytes": {"type": "integer"},
        "truncated": {"type": "boolean"},
        "canceled": {"type": "boolean"},
        "path": {"type": ["string", "null"]},
    },
    "additionalProperties": False,
}


def input_error(text, position, reason):
    line = text.count("\n", 0, position) + 1
    last = text.rfind("\n", 0, position)
    column = position - last
    raise PluginError("invalid_json", reason, line=line, column=column, offset=position)


def preflight(text, cancellation):
    """Check depth and duplicate keys while retaining precise source positions."""
    stack: list[dict[str, bool] | None] = []
    index = 0
    while index < len(text):
        if index % 4096 == 0:
            cancellation.raise_if_cancelled()
        char = text[index]
        if char in "{[":
            stack.append({} if char == "{" else None)
            if len(stack) > 128:
                input_error(text, index, "Nesting exceeds 128")
        elif char in "}]":
            if stack:
                stack.pop()
        elif char == '"':
            try:
                value, end = scan_string(text, index)
            except ValueError:
                return  # The full parser supplies the syntax error location.
            cursor = end
            while cursor < len(text) and text[cursor] in " \t\r\n":
                cursor += 1
            if cursor < len(text) and text[cursor] == ":" and stack and stack[-1] is not None:
                current = stack[-1]
                assert current is not None
                if value in current:
                    input_error(text, index, "Duplicate object key")
                current[value] = True
            index = end
            continue
        elif text.startswith(("NaN", "Infinity", "-Infinity"), index):
            input_error(text, index, "Nonfinite numbers are not JSON")
        index += 1


def transform(text, *, indent=2, sort_keys=False, minify=False, cancellation):
    if len(text.encode("utf-8")) > MAX_INPUT:
        raise PluginError("input_too_large", "Input exceeds 20 MiB")
    cancellation.raise_if_cancelled()
    preflight(text, cancellation)
    # The worker is a dedicated process; do not change the host's integer policy.
    if hasattr(sys, "set_int_max_str_digits"):
        sys.set_int_max_str_digits(0)
    try:
        value = json.loads(text, use_decimal=True, allow_nan=False)
    except json.JSONDecodeError as error:
        input_error(text, error.pos, "Invalid JSON")
    cancellation.raise_if_cancelled()
    encoder = json.JSONEncoder(
        ensure_ascii=False,
        use_decimal=True,
        allow_nan=False,
        indent=None if minify else indent,
        sort_keys=sort_keys,
        separators=(",", ":") if minify else (",", ": "),
    )
    chunks = []
    size = 0
    for chunk in encoder.iterencode(value):
        cancellation.raise_if_cancelled()
        size += len(chunk.encode("utf-8"))
        if size > MAX_OUTPUT:
            raise PluginError("output_too_large", "Output exceeds 200 MiB")
        chunks.append(chunk)
    result = "".join(chunks)
    cancellation.raise_if_cancelled()
    return result


class JsonTools:
    def activate(self, context):
        self.context = context
        language = context.locale.replace("-", "_")
        resource = files("pydesk_json_tools").joinpath(
            "locales", language, "LC_MESSAGES", "org.pydesk.json-tools.mo"
        )
        self._translator = gettext.NullTranslations()
        if resource.is_file():
            with resource.open("rb") as stream:
                self._translator = gettext.GNUTranslations(stream)
        self.export = context.cache_dir / "export"
        self.export.mkdir(parents=True, exist_ok=True)

    def t(self, text):
        return self._translator.gettext(text)

    def describe(self):
        commands = []
        for identifier, title, effects in (
            ("format", "Format JSON", "pure"),
            ("minify", "Minify JSON", "pure"),
            ("import", "Import JSON", "read"),
            ("copy", "Copy result", "external"),
            ("export", "Export JSON", "write"),
        ):
            schema = (
                INPUT
                if identifier in ("format", "minify", "import")
                else {
                    "type": "object",
                    "properties": {"artifact_id": STR},
                    "required": ["artifact_id"],
                    "additionalProperties": False,
                }
            )
            commands.append(
                {
                    "id": identifier,
                    "title": self.t(title),
                    "description": self.t(title),
                    "input_schema": schema,
                    "output_schema": OUTPUT,
                    "effects": effects,
                    "retry": "safe" if effects == "pure" else "manual",
                    "timeout_ms": 300000,
                }
            )
        return {"commands": commands}

    def _read(self, path):
        with Path(path).open("rb") as stream:
            data = stream.read(MAX_INPUT + 1)
        if len(data) > MAX_INPUT:
            raise PluginError("input_too_large", self.t("Input exceeds 20 MiB"))
        try:
            return data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise PluginError("invalid_encoding", "Expected a UTF-8 file") from None

    def invoke(self, command_id, arguments, context):
        context.cancellation.raise_if_cancelled()
        if command_id == "copy":
            context.host.call("clipboard.write", artifact_id=arguments["artifact_id"])
            return CommandResult({})
        if command_id == "export":
            path = context.host.call(
                "dialogs.save_file",
                title=self.t("Export JSON"),
                suggested_name="formatted.json",
                artifact_id=arguments["artifact_id"],
            )
            return CommandResult({"path": path, "canceled": path is None})
        if command_id == "import":
            path = context.host.choose_file(title=self.t("Import JSON"))
            if path is None:
                return CommandResult({"canceled": True})
            text = self._read(path)
        elif command_id in ("format", "minify"):
            if ("text" in arguments) == ("artifact_id" in arguments):
                raise PluginError("invalid_input", "Supply exactly one of text or artifact_id")
            text = arguments.get("text")
            if text is None:
                text = self._read(
                    context.host.call("artifacts.read", artifact_id=arguments["artifact_id"])
                )
        else:
            raise PluginError("unknown_command", "Unknown JSON command")
        try:
            output = transform(
                text,
                indent=arguments.get("indent", 2),
                sort_keys=arguments.get("sort_keys", False),
                minify=command_id == "minify",
                cancellation=context.cancellation,
            )
        except PluginError as error:
            error.args = (self.t(str(error)),)
            raise
        payload = output.encode("utf-8")
        relative = uuid.uuid4().hex + ".json"
        path = self.export / relative
        try:
            path.write_bytes(payload)
            identifier = context.host.call("artifacts.import", relative_path=relative)
        finally:
            path.unlink(missing_ok=True)
        truncated = len(payload) > PREVIEW
        preview = payload[: PREVIEW - 256].decode("utf-8", errors="ignore") if truncated else output
        if truncated:
            preview += "\n\n" + self.t("Preview truncated; copy or export the complete result.")
        result = {"artifact_id": identifier, "bytes": len(payload), "truncated": truncated}
        if len(payload) <= INLINE:
            result["text"] = output
        context.report_progress(1.0, self.t("JSON result"))
        return CommandResult(
            result,
            {
                "type": "detail",
                "title": self.t("JSON result"),
                "body": preview,
                "format": "code",
                "actions": [
                    {
                        "id": "copy",
                        "label": self.t("Copy result"),
                        "command_id": "copy",
                        "arguments": {"artifact_id": identifier},
                    },
                    {
                        "id": "export",
                        "label": self.t("Export JSON"),
                        "command_id": "export",
                        "arguments": {"artifact_id": identifier},
                    },
                ],
            },
        )

    def deactivate(self):
        pass


def create_plugin():
    return JsonTools()
