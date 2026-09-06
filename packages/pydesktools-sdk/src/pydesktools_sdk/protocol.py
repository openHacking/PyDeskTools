"""Bounded strict JSON-RPC framing and schema/view validation."""

import json
import math
from typing import Any

from .api import PluginError

MAX_FRAME = 1024 * 1024
MAX_DEPTH = 32


def reject_constant(value):
    raise ValueError("Nonfinite JSON number")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def depth_check(value, depth=0):
    if depth > MAX_DEPTH:
        raise ValueError("JSON nesting exceeds protocol limit")
    if isinstance(value, dict):
        for child in value.values():
            depth_check(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            depth_check(child, depth + 1)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Nonfinite JSON number")


def encode(message):
    depth_check(message)
    data = (
        json.dumps(message, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n"
    ).encode()
    if len(data) > MAX_FRAME:
        raise ValueError("RPC frame exceeds 1 MiB")
    return data


def read(stream):
    data = stream.readline(MAX_FRAME + 1)
    if not data:
        raise EOFError("Worker pipe closed")
    if len(data) > MAX_FRAME or not data.endswith(b"\n") or data.startswith(b"\xef\xbb\xbf"):
        raise ValueError("Invalid RPC framing")
    message = json.loads(
        data.decode("utf-8"), object_pairs_hook=unique_object, parse_constant=reject_constant
    )
    depth_check(message)
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        raise ValueError("Expected JSON-RPC object")
    if "id" in message and (
        not isinstance(message["id"], str) or not message["id"].startswith(("h-", "w-"))
    ):
        raise ValueError("Invalid request identifier")
    if "method" in message:
        if not isinstance(message["method"], str) or not isinstance(
            message.get("params", {}), dict
        ):
            raise ValueError("Invalid request")
        if "result" in message or "error" in message:
            raise ValueError("Request cannot contain a response")
    elif "id" not in message or (("result" in message) == ("error" in message)):
        raise ValueError("Invalid response")
    return message


TYPES: dict[str, Any] = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "null": type(None),
}
KEYS = {
    "type",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "enum",
    "minimum",
    "maximum",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "description",
    "title",
    "default",
}


def check_schema(schema, depth=0):
    if depth > 16 or not isinstance(schema, dict) or set(schema) - KEYS:
        raise ValueError("Unsupported schema")
    kinds = schema.get("type")
    if not isinstance(kinds, (str, list)):
        raise ValueError("Schema needs explicit type")
    if any(k not in TYPES for k in ([kinds] if isinstance(kinds, str) else kinds)):
        raise ValueError("Unsupported schema type")
    if "properties" in schema:
        if not isinstance(schema["properties"], dict) or len(schema["properties"]) > 100:
            raise ValueError("Invalid schema properties")
        for child in schema["properties"].values():
            check_schema(child, depth + 1)
    if "items" in schema:
        check_schema(schema["items"], depth + 1)
    if "additionalProperties" in schema and not isinstance(schema["additionalProperties"], bool):
        raise ValueError("additionalProperties must be boolean")


def validate(value, schema, path="arguments"):
    kinds = schema["type"]
    kinds = [kinds] if isinstance(kinds, str) else kinds

    def matches(kind):
        return isinstance(value, TYPES[kind]) and not (
            kind in ("integer", "number") and isinstance(value, bool)
        )

    if not any(matches(kind) for kind in kinds):
        raise PluginError("invalid_input", f"{path}: invalid type")
    if "enum" in schema and value not in schema["enum"]:
        raise PluginError("invalid_input", f"{path}: invalid choice")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        if set(schema.get("required", ())) - set(value):
            raise PluginError("invalid_input", f"{path}: missing required fields")
        if schema.get("additionalProperties") is False and set(value) - set(props):
            raise PluginError("invalid_input", f"{path}: unknown fields")
        for key in value.keys() & props.keys():
            validate(value[key], props[key], f"{path}.{key}")
    elif isinstance(value, list):
        if "items" in schema:
            for item in value:
                validate(item, schema["items"], path + "[]")
    if isinstance(value, (str, list)):
        low, high = (
            ("minLength", "maxLength") if isinstance(value, str) else ("minItems", "maxItems")
        )
        if len(value) < schema.get(low, 0) or len(value) > schema.get(high, float("inf")):
            raise PluginError("invalid_input", f"{path}: invalid length")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value) if isinstance(value, float) else False:
            raise PluginError("invalid_input", f"{path}: nonfinite number")
        if value < schema.get("minimum", float("-inf")) or value > schema.get(
            "maximum", float("inf")
        ):
            raise PluginError("invalid_input", f"{path}: outside bounds")


def descriptor(value):
    commands = value.get("commands") if isinstance(value, dict) else None
    if not isinstance(commands, list) or not 1 <= len(commands) <= 100:
        raise ValueError("Descriptor must have 1–100 commands")
    import re

    ids = set()
    for command in commands:
        identifier = command.get("id", "")
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", identifier) or identifier in ids:
            raise ValueError("Invalid command ID")
        ids.add(identifier)
        if command.get("effects") not in ("pure", "read", "write", "external") or command.get(
            "retry"
        ) not in ("safe", "manual"):
            raise ValueError("Invalid command semantics")
        if not 100 <= command.get("timeout_ms", 30000) <= 3600000:
            raise ValueError("Invalid deadline")
        for name in ("title", "description"):
            if not isinstance(command.get(name), str) or len(command[name].encode()) > 65536:
                raise ValueError("Invalid command label")
        check_schema(command["input_schema"])
        check_schema(command["output_schema"])
    encode({"jsonrpc": "2.0", "id": "h-check", "result": value})
    return {command["id"]: command for command in commands}


def validate_view(view, commands):
    if view is None:
        return
    if not isinstance(view, dict) or view.get("type") not in ("detail", "form", "list", "progress"):
        raise ValueError("Unsupported view type in this release")
    for key, value in view.items():
        if isinstance(value, str) and len(value.encode()) > 65536:
            raise ValueError("View string exceeds 64 KiB")
    if not isinstance(view.get("title"), str):
        raise ValueError("View requires title")
    if view["type"] == "detail" and (
        not isinstance(view.get("body"), str) or view.get("format", "text") not in ("text", "code")
    ):
        raise ValueError("Invalid detail")
    actions = view.get("actions", [])
    if not isinstance(actions, list) or len(actions) > 100:
        raise ValueError("Invalid actions")
    seen = set()
    for action in actions:
        if action["id"] in seen or action["command_id"] not in commands:
            raise ValueError("Invalid action")
        seen.add(action["id"])
        validate(action["arguments"], commands[action["command_id"]]["input_schema"])
