import pytest

from advi.core.structured_output import StructuredOutputError, parse_structured_output

SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {"type": "string", "enum": ["action", "conversation"]},
        "goal": {"type": "string"},
        "count": {"type": "number"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["mode", "goal"],
}


def test_parses_clean_json():
    result = parse_structured_output('{"mode":"action","goal":"open Chrome"}', SCHEMA)
    assert result.data["mode"] == "action"
    assert result.repaired is False


def test_strips_markdown_and_leading_prose():
    result = parse_structured_output(
        'Sure — here is the result:\n```json\n{"mode":"action","goal":"open Chrome"}\n```',
        SCHEMA,
    )
    assert result.data["goal"] == "open Chrome"
    assert result.repaired is True


def test_repairs_trailing_comma():
    result = parse_structured_output(
        '{"mode":"conversation","goal":"hello",}',
        SCHEMA,
    )
    assert result.data["mode"] == "conversation"
    assert result.repaired is True


def test_accepts_python_literal_style_quotes_without_inventing_fields():
    result = parse_structured_output(
        "{'mode': 'action', 'goal': 'open Chrome'}",
        SCHEMA,
    )
    assert result.data == {"mode": "action", "goal": "open Chrome"}


def test_rejects_missing_required_fields():
    with pytest.raises(StructuredOutputError):
        parse_structured_output('{"mode":"action"}', SCHEMA)


def test_rejects_wrong_enum_and_type():
    with pytest.raises(StructuredOutputError):
        parse_structured_output('{"mode":"unknown","goal":"x"}', SCHEMA)
    with pytest.raises(StructuredOutputError):
        parse_structured_output('{"mode":"action","goal":42}', SCHEMA)


def test_ignores_trailing_provider_prose_after_json():
    result = parse_structured_output(
        '{"mode":"action","goal":"open Chrome"}\nDone!',
        SCHEMA,
    )
    assert result.data["goal"] == "open Chrome"
