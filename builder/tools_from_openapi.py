"""Convert tolerant OpenAPI POST operations into Freya ``api_call`` tools."""

from __future__ import annotations

import copy
import json
import re
from typing import Any, Iterable

from .prompts import (
    TOOL_CALL_TRIGGER,
    TOOL_FIELD_DETAILS_TEMPLATE,
    TOOL_RESULT_FAILURE_MESSAGE,
    TOOL_RESULT_FALSE_FIELDS_TEMPLATE,
    TOOL_RESULT_OK_MESSAGE,
    TOOL_RESULT_UNCLEAR_MESSAGE,
    render_prompt,
)


CALL_VARIABLES = frozenset({"customer_id", "first_name", "last_name", "title", "now"})
SUPPORTED_TYPES = frozenset({"string", "number", "integer", "boolean", "array", "object"})
ALLOWED_SCHEMA_KEYS = frozenset(
    {"type", "description", "enum", "default", "items", "properties", "required"}
)
DESCRIPTION_CONSTRAINT_KEYS = frozenset(
    {
        "format", "pattern", "minimum", "maximum", "minLength", "maxLength",
        "minItems", "maxItems", "multipleOf", "exclusiveMinimum", "exclusiveMaximum",
    }
)


def _post_process_code() -> str:
    code = """try:
    if isinstance(result, dict):
        result.pop('header', None)
        raw_data = result.get('data')
        data_was_dict = isinstance(raw_data, dict)
        data = raw_data
        if not data_was_dict:
            data = {}
            result['data'] = data
        ok_present = 'ok' in data
        ok_value = data.get('ok')
        ok_true = ok_value is True or str(ok_value).lower() == 'true'
        ok_failed = ok_value is False or str(ok_value).lower() == 'false'
        status_value = result.get('status_code')
        http_known = False
        http_ok = False
        http_failed = False
        try:
            status_number = int(status_value)
            http_known = True
            http_ok = 200 <= status_number < 300
            http_failed = status_number < 200 or status_number >= 300
        except Exception:
            pass
        status_text = str(result.get('status') or '').strip().lower()
        status_failed = status_text in ('error', 'failed', 'failure')
        error_value = data.get('error') if data.get('error') not in (None, '', False) else result.get('error')
        has_error = error_value not in (None, '', False)
        if http_failed or status_failed or has_error or not ok_present or not data_was_dict:
            data['ok'] = False
            ok_present = True
            ok_value = False
            ok_true = False
            ok_failed = True
        false_fields = sorted(
            str(key) for key, value in data.items()
            if key not in ('ok', 'what_to_do_next')
            and (value is False or str(value).lower() == 'false')
        )
        if ok_failed or http_failed or status_failed or has_error:
            data['what_to_do_next'] = __FAILURE_MESSAGE__
        elif false_fields:
            data['what_to_do_next'] = __FALSE_FIELDS_TEMPLATE__.replace('{fields}', ', '.join(false_fields))
        elif data_was_dict and http_known and http_ok and ok_present and ok_true and status_text in ('', 'success', 'ok'):
            data['what_to_do_next'] = __OK_MESSAGE__
        else:
            data['what_to_do_next'] = __UNCLEAR_MESSAGE__
except Exception:
    pass
"""
    return (
        code.replace("__FAILURE_MESSAGE__", repr(TOOL_RESULT_FAILURE_MESSAGE.text))
        .replace("__FALSE_FIELDS_TEMPLATE__", repr(TOOL_RESULT_FALSE_FIELDS_TEMPLATE.text))
        .replace("__OK_MESSAGE__", repr(TOOL_RESULT_OK_MESSAGE.text))
        .replace("__UNCLEAR_MESSAGE__", repr(TOOL_RESULT_UNCLEAR_MESSAGE.text))
    )


POST_PROCESS_CODE = _post_process_code()


class OpenAPIError(ValueError):
    """Raised only when a required top-level OpenAPI input cannot be used."""


def _warn(warnings: list[str] | None, message: str) -> None:
    if warnings is not None:
        warnings.append(message)


def _resolve_local_ref(document: dict[str, Any], value: Any) -> Any:
    """Resolve local JSON Pointer references without mutating the document."""
    seen: set[str] = set()
    while isinstance(value, dict) and "$ref" in value:
        reference = value["$ref"]
        if not isinstance(reference, str) or not reference.startswith("#/"):
            raise ValueError(f"only local OpenAPI references are supported: {reference!r}")
        if reference in seen:
            raise ValueError(f"cyclic OpenAPI reference: {reference}")
        seen.add(reference)
        target: Any = document
        for raw_part in reference[2:].split("/"):
            part = raw_part.replace("~1", "/").replace("~0", "~")
            target = target[part]
        siblings = {key: item for key, item in value.items() if key != "$ref"}
        if siblings:
            if not isinstance(target, dict):
                raise ValueError(f"referenced value cannot be extended: {reference}")
            target = {**target, **siblings}
        value = target
    return value


def _request_schema(
    document: dict[str, Any], operation: dict[str, Any], path: str, warnings: list[str] | None
) -> dict[str, Any]:
    try:
        request_body = _resolve_local_ref(document, operation.get("requestBody", {}))
        if not isinstance(request_body, dict):
            raise TypeError("requestBody is not an object")
        content = request_body.get("content", {})
        if not isinstance(content, dict):
            raise TypeError("requestBody.content is not an object")
        media = content.get("application/json")
        if media is None and content:
            media = next(iter(content.values()))
        if media is None:
            return {"type": "object", "properties": {}, "required": []}
        media = _resolve_local_ref(document, media)
        if not isinstance(media, dict):
            raise TypeError("request media definition is not an object")
        schema = _resolve_local_ref(document, media.get("schema", {}))
        if not isinstance(schema, dict):
            raise TypeError("request schema is not an object")
        return _merge_all_of(document, schema, path + ".request", warnings)
    except Exception as exc:
        _warn(warnings, f"{path}: request schema could not be parsed ({type(exc).__name__}); using an empty body")
        return {"type": "object", "properties": {}, "required": []}


def _enum_type(values: Any) -> str | None:
    if not isinstance(values, list):
        return None
    non_null = [value for value in values if value is not None]
    if not non_null:
        return None
    inferred = set()
    for value in non_null:
        if isinstance(value, bool):
            inferred.add("boolean")
        elif isinstance(value, int):
            inferred.add("integer")
        elif isinstance(value, float):
            inferred.add("number")
        elif isinstance(value, str):
            inferred.add("string")
        else:
            return None
    if inferred == {"integer", "number"}:
        return "number"
    return next(iter(inferred)) if len(inferred) == 1 else None


def _plain_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        text = str(value)
    return text if len(text) <= 240 else text[:237] + "..."


def _merge_all_of(
    document: dict[str, Any], schema: dict[str, Any], field_path: str, warnings: list[str] | None
) -> dict[str, Any]:
    """Flatten compatible ``allOf`` object fragments without losing their fields."""
    raw_parts = schema.get("allOf")
    if raw_parts is None:
        return schema
    if not isinstance(raw_parts, list):
        _warn(warnings, f"{field_path}: allOf is not an array; ignoring it")
        return {key: value for key, value in schema.items() if key != "allOf"}
    merged = {key: copy.deepcopy(value) for key, value in schema.items() if key != "allOf"}
    descriptions: list[str] = []
    if merged.get("description"):
        descriptions.append(str(merged["description"]).strip())
    for index, raw_part in enumerate(raw_parts):
        try:
            part = _resolve_local_ref(document, raw_part)
            if not isinstance(part, dict):
                raise TypeError("allOf member is not an object")
            part = _merge_all_of(document, part, f"{field_path}.allOf[{index}]", warnings)
        except Exception as exc:
            _warn(warnings, f"{field_path}.allOf[{index}]: could not be merged ({type(exc).__name__})")
            continue
        if part.get("description"):
            descriptions.append(str(part["description"]).strip())
        if isinstance(part.get("properties"), dict):
            target_properties = merged.setdefault("properties", {})
            if not isinstance(target_properties, dict):
                _warn(warnings, f"{field_path}: allOf properties conflict; using object properties")
                target_properties = {}
                merged["properties"] = target_properties
            target_properties.update(copy.deepcopy(part["properties"]))
        if isinstance(part.get("required"), list):
            target_required = merged.setdefault("required", [])
            if not isinstance(target_required, list):
                target_required = []
                merged["required"] = target_required
            for name in part["required"]:
                if name not in target_required:
                    target_required.append(copy.deepcopy(name))
        part_type = part.get("type")
        if part_type is not None:
            if "type" in merged and merged["type"] != part_type:
                _warn(warnings, f"{field_path}: conflicting allOf types; keeping {merged['type']!r}")
            else:
                merged["type"] = copy.deepcopy(part_type)
        for key, value in part.items():
            if key not in {"description", "properties", "required", "type"} and key not in merged:
                merged[key] = copy.deepcopy(value)
    if descriptions:
        merged["description"] = " ".join(dict.fromkeys(descriptions))
    _warn(warnings, f"{field_path}: merged allOf schema")
    return merged


def _alternative_summary(document: dict[str, Any], value: Any) -> str:
    if not isinstance(value, list):
        return "alternatives"
    summaries = []
    for raw in value[:6]:
        try:
            option = _resolve_local_ref(document, raw)
        except Exception:
            option = raw
        if isinstance(option, dict):
            if isinstance(option.get("enum"), list):
                summaries.append("enum " + "/".join(str(item) for item in option["enum"][:6]))
            elif option.get("type"):
                summaries.append(str(option["type"]))
            elif option.get("properties"):
                summaries.append("object")
        elif option is not None:
            summaries.append(type(option).__name__)
    return " or ".join(dict.fromkeys(summaries)) or "alternatives"


def _normalise_type(schema: dict[str, Any], field_path: str, warnings: list[str] | None) -> tuple[str, bool]:
    raw_type = schema.get("type")
    nullable = schema.get("nullable") is True
    if isinstance(raw_type, list):
        nullable = nullable or "null" in raw_type
        candidates = [item for item in raw_type if item != "null"]
        supported = [item for item in candidates if isinstance(item, str) and item in SUPPORTED_TYPES]
        if supported:
            if len(supported) > 1:
                _warn(warnings, f"{field_path}: multiple non-null types found; using {supported[0]!r}")
            return supported[0], nullable
        _warn(warnings, f"{field_path}: type list had no supported non-null type; using 'string'")
        return "string", nullable
    if isinstance(raw_type, str) and raw_type in SUPPORTED_TYPES:
        return raw_type, nullable
    if raw_type is None:
        inferred = _enum_type(schema.get("enum"))
        if "properties" in schema:
            fallback = "object"
        elif "items" in schema:
            fallback = "array"
        else:
            fallback = inferred or "string"
        _warn(warnings, f"{field_path}: type is missing; using {fallback!r}")
        return fallback, nullable or (isinstance(schema.get("enum"), list) and None in schema["enum"])
    _warn(warnings, f"{field_path}: unsupported type {raw_type!r}; using 'string'")
    return "string", nullable


def _copy_schema(
    document: dict[str, Any], raw_schema: Any, field_path: str, warnings: list[str] | None
) -> dict[str, Any]:
    try:
        schema = _resolve_local_ref(document, raw_schema)
        if not isinstance(schema, dict):
            raise TypeError("field schema is not an object")
        schema = _merge_all_of(document, schema, field_path, warnings)
    except Exception as exc:
        _warn(warnings, f"{field_path}: schema could not be parsed ({type(exc).__name__}); using 'string'")
        return {"type": "string", "description": "Input constraints could not be read from the OpenAPI file."}

    schema_type, nullable = _normalise_type(schema, field_path, warnings)
    result: dict[str, Any] = {"type": schema_type}
    description_parts = []
    if schema.get("description"):
        description_parts.append(str(schema["description"]).strip())

    enum = schema.get("enum")
    if isinstance(enum, list):
        clean_enum = [copy.deepcopy(value) for value in enum if value is not None]
        if clean_enum:
            result["enum"] = clean_enum
        if len(clean_enum) != len(enum):
            nullable = True
    elif enum is not None:
        _warn(warnings, f"{field_path}: enum is not an array; ignoring it")
        description_parts.append(f"enum constraint: {_plain_value(enum)}")

    structural = {
        "type", "description", "enum", "items", "properties", "required", "default", "$ref",
        "allOf", "oneOf", "anyOf",
    }
    for key, value in schema.items():
        if key in DESCRIPTION_CONSTRAINT_KEYS:
            description_parts.append(f"{key}: {_plain_value(value)}")
            _warn(warnings, f"{field_path}: moved unsupported schema key {key!r} into the description")
        elif key not in structural:
            _warn(warnings, f"{field_path}: ignored non-constraint schema key {key!r}")
    for key in ("oneOf", "anyOf"):
        if key in schema:
            description_parts.append(f"{key}: {_alternative_summary(document, schema[key])}")
            _warn(warnings, f"{field_path}: summarized {key} alternatives in the description")
    if nullable and not any(part.startswith("nullable:") for part in description_parts):
        description_parts.append("nullable: true")
        _warn(warnings, f"{field_path}: moved nullable constraint into the description")

    if "items" in schema:
        result["items"] = _copy_schema(document, schema["items"], f"{field_path}[]", warnings)
    elif schema_type == "array":
        _warn(warnings, f"{field_path}: array items are missing; using string items")
        result["items"] = {"type": "string"}

    if "properties" in schema:
        nested = schema["properties"]
        if isinstance(nested, dict):
            result["properties"] = {
                str(name): _copy_schema(document, child, f"{field_path}.{name}", warnings)
                for name, child in nested.items()
            }
        else:
            _warn(warnings, f"{field_path}: properties is not an object; ignoring it")

    if "required" in schema:
        required = schema["required"]
        if isinstance(required, list):
            result["required"] = [str(name) for name in required]
        else:
            _warn(warnings, f"{field_path}: required is not an array; ignoring it")

    if description_parts:
        result["description"] = " ".join(description_parts)
    return result


def _body_property(
    document: dict[str, Any],
    tool_name: str,
    name: str,
    raw_schema: Any,
    warnings: list[str] | None,
    baked_fields: frozenset[str],
    known_entry_variables: frozenset[str],
) -> dict[str, Any]:
    result = _copy_schema(document, raw_schema, f"{tool_name}.{name}", warnings)
    if name in baked_fields:
        placeholder = name
    elif name in known_entry_variables:
        placeholder = f"{tool_name}_{name}"
        _warn(warnings, f"{tool_name}.{name}: renamed model placeholder to avoid a node-entry variable collision")
    else:
        placeholder = name
    result["default"] = "{{" + placeholder + "}}"
    return result


def _description(operation: dict[str, Any], properties: dict[str, Any]) -> str:
    summary = str(operation.get("summary") or operation.get("description") or "perform this API operation").strip()
    parts = [summary, TOOL_CALL_TRIGGER.text]
    field_details = []
    for name, schema in properties.items():
        if not isinstance(schema, dict) or not schema.get("description"):
            continue
        detail = str(schema["description"]).strip()
        field_details.append(detail if detail.startswith("format:") else f"{name}: {detail}")
    if field_details:
        parts.append(render_prompt(TOOL_FIELD_DETAILS_TEMPLATE, field_details="; ".join(field_details)))
    return " ".join(part for part in parts if part)


def _unique_tool_name(path: str, used: set[str], index: int, warnings: list[str] | None) -> str:
    base = re.sub(r"[^A-Za-z0-9_]+", "_", path.strip("/")).strip("_")
    if not base:
        base = f"post_tool_{index}"
        _warn(warnings, f"{path!r}: path produced an empty tool name; using {base!r}")
    name = base
    suffix = 2
    while name in used:
        name = f"{base}_{suffix}"
        suffix += 1
    if name != base:
        _warn(warnings, f"{path!r}: duplicate tool name {base!r}; using {name!r}")
    used.add(name)
    return name


def tools_from_openapi(
    document: dict[str, Any],
    warnings: list[str] | None = None,
    *,
    baked_fields: Iterable[str] = CALL_VARIABLES,
    known_entry_variables: Iterable[str] = CALL_VARIABLES,
) -> list[dict[str, Any]]:
    """Return one tolerant Freya tool for every POST path in an OpenAPI document."""
    servers = document.get("servers")
    if not isinstance(servers, list) or not servers or not isinstance(servers[0], dict):
        raise OpenAPIError("OpenAPI servers[0].url is required")
    base_url = servers[0].get("url")
    if not isinstance(base_url, str) or not base_url:
        raise OpenAPIError("OpenAPI servers[0].url is required")
    paths = document.get("paths")
    if not isinstance(paths, dict):
        _warn(warnings, "OpenAPI paths is not an object; no tools were generated")
        return []

    baked = frozenset(baked_fields)
    entry_variables = frozenset(known_entry_variables)
    tools: list[dict[str, Any]] = []
    tool_names: set[str] = set()
    for index, (raw_path, raw_path_item) in enumerate(paths.items(), start=1):
        path = str(raw_path)
        try:
            path_item = _resolve_local_ref(document, raw_path_item)
        except Exception as exc:
            _warn(warnings, f"{path}: path item could not be parsed ({type(exc).__name__}); skipping it")
            continue
        if not isinstance(path_item, dict) or "post" not in path_item:
            continue
        if path_item.get("parameters"):
            _warn(warnings, f"{path}: path-item parameters are unsupported and were ignored")
        try:
            operation = _resolve_local_ref(document, path_item["post"])
        except Exception as exc:
            _warn(warnings, f"{path}: POST operation could not be parsed ({type(exc).__name__}); using defaults")
            operation = {}
        if not isinstance(operation, dict):
            _warn(warnings, f"{path}: POST operation is not an object; using defaults")
            operation = {}

        name = _unique_tool_name(path, tool_names, index, warnings)
        schema = _request_schema(document, operation, path, warnings)
        raw_properties = schema.get("properties", {})
        if not isinstance(raw_properties, dict):
            _warn(warnings, f"{path}: request properties is not an object; using an empty body")
            raw_properties = {}
        properties = {
            str(field_name): _body_property(
                document,
                name,
                str(field_name),
                field_schema,
                warnings,
                baked,
                entry_variables,
            )
            for field_name, field_schema in raw_properties.items()
        }
        required = schema.get("required", [])
        if not isinstance(required, list):
            _warn(warnings, f"{path}: request required is not an array; ignoring it")
            required = []
        required = [str(field_name) for field_name in required if str(field_name) not in baked]
        body_schema: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            body_schema["required"] = required

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
                                "properties": {"Content-Type": {"type": "string", "default": "application/json"}},
                            },
                            "body": body_schema,
                        },
                    },
                },
                "post_process_code": POST_PROCESS_CODE,
            }
        )
    return tools


def _contract_fields(document: dict[str, Any], schema: Any, depth: int = 0) -> dict[str, Any]:
    """Compact field view of an object schema: type, enum, description, nested items."""
    try:
        schema = _merge_all_of(document, _resolve_local_ref(document, schema), "contract", None)
    except Exception:
        return {}
    properties = schema.get("properties") if isinstance(schema, dict) else None
    if not isinstance(properties, dict):
        return {}
    required = schema.get("required") if isinstance(schema.get("required"), list) else []
    fields: dict[str, Any] = {}
    for name, raw in properties.items():
        try:
            prop = _merge_all_of(document, _resolve_local_ref(document, raw), "contract", None)
        except Exception:
            prop = {}
        if not isinstance(prop, dict):
            prop = {}
        entry: dict[str, Any] = {"type": prop.get("type") or ""}
        if isinstance(prop.get("enum"), list):
            entry["enum"] = list(prop["enum"])
        if prop.get("format"):
            entry["format"] = prop["format"]
        if prop.get("description"):
            entry["description"] = str(prop["description"])
        if name in required:
            entry["required"] = True
        if depth < 3:
            if prop.get("type") == "array":
                items = _contract_fields(document, prop.get("items", {}), depth + 1)
                if items:
                    entry["items"] = items
            elif prop.get("type") == "object" or isinstance(prop.get("properties"), dict):
                nested = _contract_fields(document, prop, depth + 1)
                if nested:
                    entry["properties"] = nested
        fields[str(name)] = entry
    return fields


def _response_schema(document: dict[str, Any], operation: dict[str, Any]) -> Any:
    responses = operation.get("responses")
    if not isinstance(responses, dict):
        return {}
    for code in ("200", "201", 200, 201):
        response = responses.get(code)
        if response is None:
            continue
        try:
            response = _resolve_local_ref(document, response)
            content = response.get("content", {}) if isinstance(response, dict) else {}
            media = content.get("application/json") or (next(iter(content.values())) if content else {})
            return _resolve_local_ref(document, media).get("schema", {})
        except Exception:
            return {}
    return {}


def tool_contract(document: dict[str, Any]) -> dict[str, Any]:
    """Tool name -> {summary, request fields, response fields}, using the same names as
    ``tools_from_openapi``. Builder-time input for spec extraction and its validation."""
    paths = document.get("paths")
    if not isinstance(paths, dict):
        return {}
    contract: dict[str, Any] = {}
    used: set[str] = set()
    for index, (raw_path, raw_item) in enumerate(paths.items(), start=1):
        try:
            item = _resolve_local_ref(document, raw_item)
            if not isinstance(item, dict) or "post" not in item:
                continue
            operation = _resolve_local_ref(document, item["post"])
        except Exception:
            continue
        if not isinstance(operation, dict):
            operation = {}
        name = _unique_tool_name(str(raw_path), used, index, None)
        contract[name] = {
            "summary": str(operation.get("summary") or operation.get("description") or ""),
            "request": _contract_fields(document, _request_schema(document, operation, str(raw_path), None)),
            "response": _contract_fields(document, _response_schema(document, operation)),
        }
    return contract


def contract_field_kind(entry: Any) -> str:
    """JSON schema type of one ``tool_contract`` field entry ('' when unknown)."""
    return str(entry.get("type") or "") if isinstance(entry, dict) else ""
