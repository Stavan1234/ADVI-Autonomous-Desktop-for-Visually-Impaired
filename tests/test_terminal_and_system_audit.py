from pathlib import Path

from advi.core.system_audit import ADVISystemAuditor
from advi.io.terminal_trace import TerminalTraceRenderer


def test_terminal_trace_is_compact_and_does_not_print_model_reasoning(capsys):
    class Decision:
        mode = "action"
        action = "search"
        confidence = 0.91

    class Action:
        action = "search"
        parameters = {"query": "ADVI project"}

    class Plan:
        actions = [Action()]

    class Result:
        action = "search"
        success = True
        verification_status = "verified"

    TerminalTraceRenderer(enabled=True).render(
        user_input="search for ADVI project",
        decision=Decision(),
        plan=Plan(),
        results=[Result()],
        response="I found the result.",
    )
    out = capsys.readouterr().out
    assert "search for ADVI project" in out
    assert "action → search" in out
    assert "1. search" in out
    assert "✓ search, verified" in out
    assert "I found the result." in out
    assert "╭" in out and "╰" in out


def test_terminal_trace_can_be_disabled(capsys):
    TerminalTraceRenderer(enabled=False).render(user_input="hello", response="hi")
    assert capsys.readouterr().out == ""


def test_system_audit_imports_production_path():
    report = ADVISystemAuditor().run()
    names = {check.name for check in report.checks}
    assert "import:advi.app" in names
    assert "import:advi.brain.agent" in names
    assert "speech_input" in names


def test_console_logging_keeps_info_out_of_terminal(monkeypatch, tmp_path):
    import logging
    from advi.core.logging import configure_logging

    root = logging.getLogger()
    old_handlers = list(root.handlers)
    root.handlers.clear()
    try:
        configure_logging(tmp_path / "logs")
        levels = {type(h).__name__: h.level for h in root.handlers}
        assert any(level >= logging.WARNING for name, level in levels.items() if name == "StreamHandler")
        assert any(level == logging.INFO for name, level in levels.items() if name == "FileHandler")
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers.clear()
        root.handlers.extend(old_handlers)
