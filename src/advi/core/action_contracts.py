from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .action_plan import Action


@dataclass(frozen=True)
class ParameterRule:
    required: bool = False
    aliases: tuple[str, ...] = ()
    kind: str = "string"  # string, number, integer, bool, list, object


@dataclass(frozen=True)
class ActionContract:
    action: str
    parameters: dict[str, ParameterRule] = field(default_factory=dict)
    allow_target_fallback: bool = False


ACTION_CONTRACTS: dict[str, ActionContract] = {
    "open_application": ActionContract("open_application", {"application": ParameterRule(required=True, aliases=("app", "name"))}, True),
    "focus_window": ActionContract("focus_window", {"title": ParameterRule(required=True, aliases=("window", "name"))}, True),
    "close_window": ActionContract("close_window", {}, True),
    "type_text": ActionContract("type_text", {"text": ParameterRule(required=True, aliases=("value", "content"))}),
    "press_key": ActionContract("press_key", {"key": ParameterRule(required=True, aliases=("value",))}, True),
    "hotkey": ActionContract("hotkey", {"keys": ParameterRule(required=True, aliases=("hotkey",), kind="list_or_string")}),
    "click": ActionContract("click", {}, True),
    "double_click": ActionContract("double_click", {}, True),
    "right_click": ActionContract("right_click", {}, True),
    "scroll": ActionContract("scroll", {"amount": ParameterRule(kind="integer"), "direction": ParameterRule(kind="string")}),
    "wait": ActionContract("wait", {"duration": ParameterRule(kind="number", aliases=("seconds",))}),
    "finish": ActionContract("finish"),
    "navigate": ActionContract("navigate", {"url": ParameterRule(required=True)}, True),
    "search": ActionContract("search", {"query": ParameterRule(required=True, aliases=("value",))}),
    "click_web_element": ActionContract("click_web_element", {"selector": ParameterRule(required=True)}, True),
    "read_web_page": ActionContract("read_web_page"),
    "research_web": ActionContract(
        "research_web",
        {
            "query": ParameterRule(required=True),
            "target": ParameterRule(aliases=("site",)),
            "max_chars": ParameterRule(aliases=("limit",), kind="integer"),
        },
    ),
    "research_web_multi": ActionContract(
        "research_web_multi",
        {
            "query": ParameterRule(required=True),
            "target": ParameterRule(aliases=("site",)),
            "max_sources": ParameterRule(kind="integer"),
            "pages": ParameterRule(kind="integer"),
            "max_chars": ParameterRule(aliases=("limit",), kind="integer"),
        },
    ),
    "save_file": ActionContract("save_file", {"path": ParameterRule(required=True, aliases=("filename",)), "content": ParameterRule(required=True, aliases=("value",))}, True),
    "create_file": ActionContract("create_file", {"path": ParameterRule(required=True, aliases=("filename",)), "content": ParameterRule(required=True, aliases=("value",))}, True),
    "append_file": ActionContract("append_file", {"path": ParameterRule(required=True, aliases=("filename",)), "content": ParameterRule(required=True, aliases=("value",))}, True),
    "replace_file_text": ActionContract("replace_file_text", {"path": ParameterRule(required=True, aliases=("filename",)), "old_text": ParameterRule(required=True, aliases=("old", "find")), "new_text": ParameterRule(required=True, aliases=("new", "replace", "value"))}, True),
    "read_file": ActionContract("read_file", {"path": ParameterRule(required=True, aliases=("filename",))}, True),
    "delete_file": ActionContract("delete_file", {"path": ParameterRule(required=True)}, True),
    "list_files": ActionContract("list_files", {"directory": ParameterRule(aliases=("path",))}, True),
    "email_draft_create": ActionContract("email_draft_create", {"to": ParameterRule(required=True, aliases=("recipient",)), "subject": ParameterRule(required=True), "body": ParameterRule(required=True, aliases=("content",))}),
    "email_draft_read": ActionContract("email_draft_read", {"draft_id": ParameterRule(required=True)}, True),
    "email_draft_update": ActionContract("email_draft_update", {"draft_id": ParameterRule(required=True), "to": ParameterRule(aliases=("recipient",)), "subject": ParameterRule(), "body": ParameterRule(aliases=("content",))}, True),
    "email_send": ActionContract("email_send", {"to": ParameterRule(required=False, aliases=("recipient",)), "subject": ParameterRule(required=False), "body": ParameterRule(required=False, aliases=("content",)), "draft_id": ParameterRule()}, True),
    "email_read": ActionContract("email_read", {"query": ParameterRule(kind="string"), "limit": ParameterRule(kind="integer")}),
    "memory_retrieval": ActionContract("memory_retrieval", {"query": ParameterRule(required=True)}, True),
    "memory_update": ActionContract("memory_update", {"fact": ParameterRule(required=True, aliases=("content", "value")), "category": ParameterRule(), "key": ParameterRule()}),
    "memory_forget": ActionContract("memory_forget", {"fact": ParameterRule(aliases=("key",))}, True),
}


def get_action_contract(action: str) -> ActionContract | None:
    return ACTION_CONTRACTS.get(action.strip())


def validate_and_normalize_action(action: Action) -> tuple[Action | None, list[str]]:
    """Canonicalize known parameter aliases and reject materially incomplete actions."""
    contract = get_action_contract(action.action)
    if contract is None:
        return action, []

    params = dict(action.parameters or {})
    errors: list[str] = []

    for name, rule in contract.parameters.items():
        if name not in params or params.get(name) in (None, ""):
            for alias in rule.aliases:
                if params.get(alias) not in (None, ""):
                    params[name] = params[alias]
                    break

        value = params.get(name)
        if rule.required and value in (None, ""):
            if contract.allow_target_fallback and action.target:
                params[name] = action.target
            else:
                errors.append(f"Missing required parameter '{name}'.")
                continue

        if value is not None and value != "":
            try:
                _validate_kind(name, value, rule.kind)
            except ValueError as exc:
                errors.append(str(exc))

    normalized = action.model_copy(update={"parameters": params})
    return (normalized if not errors else None), errors


def _validate_kind(name: str, value: Any, kind: str) -> None:
    if kind == "string":
        if not isinstance(value, str):
            raise ValueError(f"Parameter '{name}' must be a string.")
    elif kind == "integer":
        try:
            int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Parameter '{name}' must be an integer.") from exc
    elif kind == "number":
        try:
            float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Parameter '{name}' must be numeric.") from exc
    elif kind == "list_or_string":
        if not isinstance(value, (list, tuple, str)):
            raise ValueError(f"Parameter '{name}' must be a list or string.")
