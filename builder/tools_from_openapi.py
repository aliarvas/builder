"""Convert OpenAPI POST operations into Freya ``api_call`` tools."""

from __future__ import annotations

import copy
import re
from typing import Any


CALL_VARIABLES = frozenset({"customer_id", "first_name", "last_name", "title", "now"})


class OpenAPIError(ValueError):
    """Raised when the supplied OpenAPI document cannot define Freya tools."""


def _resolve_local_ref(document: dict[str, Any], value: Any) -> Any:
    """Resolve local JSON Pointer references without mutating the document."""
    seen: set[str] = set()
    while isinstance(value, dict) and "$ref" in value:
        reference = value["$ref"]
        if not isinstance(reference, str) or not reference.startswith("#/"):
            raise OpenAPIError(f"only local OpenAPI references are supported: {reference!r}")
        if reference in seen:
            raise OpenAPIError(f"cyclic OpenAPI reference: {reference}")
        seen.add(reference)
        target: Any = document
        for raw_part in reference[2:].split("/"):
            part = raw_part.replace("~1", "/").replace("~0", "~")
            try:
                target = target[part]
            except (KeyError, TypeError) as exc:
                raise OpenAPIError(f"unresolved OpenAPI reference: {reference}") from exc
        siblings = {key: item for key, item in value.items() if key != "$ref"}
        if siblings:
            if not isinstance(target, dict):
                raise OpenAPIError(f"referenced value cannot be extended: {reference}")
            target = {**target, **siblings}
        value = target
    return value


def _request_schema(document: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    request_body = _resolve_local_ref(document, operation.get("requestBody", {}))
    if not isinstance(request_body, dict):
        raise OpenAPIError("requestBody must be an object")
    content = request_body.get("content", {})
    if not isinstance(content, dict):
        raise OpenAPIError("requestBody.content must be an object")
    media = content.get("application/json")
    if media is None and content:
        media = next(iter(content.values()))
    if media is None:
        return {"type": "object", "properties": {}, "required": []}
    media = _resolve_local_ref(document, media)
    if not isinstance(media, dict):
        raise OpenAPIError("request media definition must be an object")
    schema = _resolve_local_ref(document, media.get("schema", {}))
    if not isinstance(schema, dict):
        raise OpenAPIError("request schema must be an object")
    return schema


SUPPORTED_TYPES = frozenset({"string", "number", "integer", "boolean", "array", "object"})
SCHEMA_KEYS = ("enum", "pattern", "minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems")


def _schema_description(schema: dict[str, Any]) -> str:
    parts = []
    if schema.get("description"):
        parts.append(str(schema["description"]).strip())
    constraints = []
    for key in ("format", "pattern", "minimum", "maximum"):
        if key in schema:
            constraints.append(f"{key}: {schema[key]}")
    if schema.get("nullable") is True:
        constraints.append("nullable: true")
    if constraints:
        parts.append("(" + ", ".join(constraints) + ")")
    return " ".join(parts)


def _copy_schema(document: dict[str, Any], raw_schema: Any, field_path: str) -> dict[str, Any]:
    schema = _resolve_local_ref(document, raw_schema)
    if not isinstance(schema, dict):
        raise OpenAPIError(f"schema for {field_path!r} must be an object")
    result: dict[str, Any] = {}
    schema_type = schema.get("type")
    if schema_type is not None:
        if schema_type not in SUPPORTED_TYPES:
            raise OpenAPIError(f"unsupported OpenAPI type {schema_type!r} for {field_path!r}")
        result["type"] = schema_type
    elif not any(key in schema for key in ("allOf", "oneOf", "anyOf")):
        raise OpenAPIError(f"OpenAPI type is required for {field_path!r}")

    for key in SCHEMA_KEYS:
        if key in schema:
            result[key] = copy.deepcopy(schema[key])
    description = _schema_description(schema)
    if description:
        result["description"] = description
    if "nullable" in schema:
        result["nullable"] = bool(schema["nullable"])
    if "items" in schema:
        result["items"] = _copy_schema(document, schema["items"], f"{field_path}[]")
    if "properties" in schema:
        nested = schema["properties"]
        if not isinstance(nested, dict):
            raise OpenAPIError(f"properties for {field_path!r} must be an object")
        result["properties"] = {
            name: _copy_schema(document, child, f"{field_path}.{name}")
            for name, child in nested.items()
        }
    if "required" in schema:
        if not isinstance(schema["required"], list):
            raise OpenAPIError(f"required for {field_path!r} must be an array")
        result["required"] = copy.deepcopy(schema["required"])
    for keyword in ("allOf", "oneOf", "anyOf"):
        if keyword in schema:
            choices = schema[keyword]
            if not isinstance(choices, list):
                raise OpenAPIError(f"{keyword} for {field_path!r} must be an array")
            result[keyword] = [
                _copy_schema(document, choice, f"{field_path}.{keyword}[{index}]")
                for index, choice in enumerate(choices)
            ]
    return result


def _body_property(document: dict[str, Any], name: str, raw_schema: Any) -> dict[str, Any]:
    result = _copy_schema(document, raw_schema, name)
    result["default"] = "{{" + name + "}}"
    return result


def _description(operation: dict[str, Any], properties: dict[str, Any]) -> str:
    parts = [str(operation.get("summary") or operation.get("description") or "Call this API operation.").strip()]
    field_details = []
    for name, schema in properties.items():
        if isinstance(schema, dict) and schema.get("description"):
            field_details.append(f"{name}: {schema['description']}")
    if field_details:
        parts.append("Fields: " + "; ".join(field_details))
    return " ".join(part for part in parts if part)


def tools_from_openapi(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Return one Freya tool for every POST path in an OpenAPI document."""
    servers = document.get("servers")
    if not isinstance(servers, list) or not servers or not isinstance(servers[0], dict):
        raise OpenAPIError("OpenAPI servers[0].url is required")
    base_url = servers[0].get("url")
    if not isinstance(base_url, str) or not base_url:
        raise OpenAPIError("OpenAPI servers[0].url is required")
    paths = document.get("paths")
    if not isinstance(paths, dict):
        raise OpenAPIError("OpenAPI paths must be an object")

    tools: list[dict[str, Any]] = []
    tool_names: set[str] = set()
    for path, path_item in paths.items():
        path_item = _resolve_local_ref(document, path_item)
        if not isinstance(path, str) or not isinstance(path_item, dict) or "post" not in path_item:
            continue
        operation = _resolve_local_ref(document, path_item["post"])
        if not isinstance(operation, dict):
            raise OpenAPIError(f"POST operation for {path!r} must be an object")
        if path_item.get("parameters"):
            raise OpenAPIError(f"path-item parameters are not supported for {path!r}")
        name = re.sub(r"[^A-Za-z0-9_]+", "_", path.strip("/")).strip("_")
        if not name:
            raise OpenAPIError("a POST path cannot map to an empty tool name")
        if name in tool_names:
            raise OpenAPIError(f"POST paths produce duplicate tool name {name!r}")
        tool_names.add(name)
        schema = _request_schema(document, operation)
        raw_properties = schema.get("properties", {})
        if not isinstance(raw_properties, dict):
            raise OpenAPIError(f"request properties for {path!r} must be an object")
        properties = {
            field_name: _body_property(document, field_name, field_schema)
            for field_name, field_schema in raw_properties.items()
        }
        required = schema.get("required", [])
        if not isinstance(required, list):
            raise OpenAPIError(f"request required fields for {path!r} must be an array")
        required = [name for name in required if name not in CALL_VARIABLES]
        body_schema: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            body_schema["required"] = copy.deepcopy(required)

        tools.append(
            {
                "type": "function",
                "config": {"timeoutMs": 10000, "maxRetries": 0},
                "function": {
                    "name": name,
                    "handler": "__function__:api_call",
                    "description": _description(operation, properties),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "default": base_url.rstrip("/") + "/" + path.lstrip("/")},
                            "method": {"type": "string", "default": "POST"},
                            "headers": {
                                "type": "object",
                                "properties": {
                                    "Content-Type": {"type": "string", "default": "application/json"}
                                },
                            },
                            "body": body_schema,
                        },
                    },
                },
            }
        )
    return tools
