from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StructuredParseResult:
    data: dict[str, Any]
    source: str
    repaired: bool = False


class StructuredOutputError(ValueError):
    """Raised when an LLM response cannot be safely parsed and validated."""


def parse_structured_output(raw: str, schema: dict[str, Any]) -> StructuredParseResult:
    """Parse and minimally repair an LLM response, then validate its shape.

    Repair is deterministic and deliberately conservative: markdown fences,
    leading prose, JSON-compatible Python literals, and trailing commas are
    normalized. No semantic fields are invented.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise StructuredOutputError("Structured response is empty.")

    candidates: list[tuple[str, bool]] = []
    text = raw.strip()
    candidates.append((text, False))

    unfenced = _strip_fences(text)
    if unfenced != text:
        candidates.append((unfenced, True))

    extracted = _extract_json_object(unfenced)
    if extracted and extracted != unfenced:
        candidates.append((extracted, True))

    for candidate, repaired in candidates:
        for transformed, transformed_flag in _repair_candidates(candidate):
            parsed_with_json = True
            try:
                data = json.loads(transformed)
            except (json.JSONDecodeError, TypeError):
                parsed_with_json = False
                try:
                    data = ast.literal_eval(transformed)
                except (SyntaxError, ValueError, TypeError):
                    continue
            if not isinstance(data, dict):
                continue
            errors = validate_schema(data, schema)
            if not errors:
                return StructuredParseResult(
                    data=data,
                    source=transformed,
                    repaired=repaired or transformed_flag or not parsed_with_json,
                )

    raise StructuredOutputError(_validation_failure_message(raw, schema))


def validate_schema(data: Any, schema: dict[str, Any], path: str = "$" ) -> list[str]:
    errors: list[str] = []
    expected = schema.get("type")
    if expected is not None and not _matches_type(data, expected):
        return [f"{path}: expected {expected}, got {type(data).__name__}"]

    if "enum" in schema and data not in schema["enum"]:
        errors.append(f"{path}: value is not in enum")

    if isinstance(data, dict):
        # Required fields are enforced at the response root. Nested required
        # semantics are intentionally left to the subsystem normalizer because
        # several legacy schemas contain advisory nested slots.
        if path == "$":
            for key in schema.get("required", []):
                if key not in data:
                    errors.append(f"{path}: missing required field {key!r}")
        properties = schema.get("properties", {})
        for key, value in data.items():
            if key in properties:
                errors.extend(validate_schema(value, properties[key], f"{path}.{key}"))

    elif isinstance(data, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for idx, value in enumerate(data):
                errors.extend(validate_schema(value, item_schema, f"{path}[{idx}]"))
    return errors


def _matches_type(value: Any, expected: Any) -> bool:
    expected_types = expected if isinstance(expected, list) else [expected]
    for item in expected_types:
        if item == "null" and value is None:
            return True
        if item == "object" and isinstance(value, dict):
            return True
        if item == "array" and isinstance(value, list):
            return True
        if item == "string" and isinstance(value, str):
            return True
        if item == "boolean" and isinstance(value, bool):
            return True
        if item == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
        if item == "integer" and isinstance(value, int) and not isinstance(value, bool):
            return True
    return False


def _strip_fences(text: str) -> str:
    match = re.fullmatch(r"\s*```(?:json|javascript|js)?\s*([\s\S]*?)\s*```\s*", text, re.IGNORECASE)
    return match.group(1).strip() if match else text


def _extract_json_object(text: str) -> str | None:
    decoder = json.JSONDecoder()
    for start, char in enumerate(text):
        if char != "{":
            continue
        try:
            obj, end = decoder.raw_decode(text[start:])
            if isinstance(obj, dict):
                return text[start : start + end]
        except json.JSONDecodeError:
            continue
    return None


def _repair_candidates(text: str) -> list[tuple[str, bool]]:
    candidates: list[tuple[str, bool]] = [(text, False)]
    no_commas = re.sub(r",\s*([}\]])", r"\1", text)
    if no_commas != text:
        candidates.append((no_commas, True))
    # Common provider leakage: a JSON object followed by prose.
    extracted = _extract_json_object(text)
    if extracted and extracted != text:
        candidates.append((extracted, True))
    # Some models emit single-quoted Python literals. literal_eval is attempted
    # after json.loads, so simply retrying the original candidate is enough.
    return candidates


def _validation_failure_message(raw: str, schema: dict[str, Any]) -> str:
    preview = re.sub(r"\s+", " ", raw).strip()[:240]
    required = ", ".join(schema.get("required", [])) or "the required fields"
    return f"Invalid structured response; expected {required}. Response: {preview!r}"
