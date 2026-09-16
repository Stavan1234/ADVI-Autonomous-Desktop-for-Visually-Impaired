from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AuditCheck:
    name: str
    status: str
    detail: str


@dataclass
class SystemAuditReport:
    checks: list[AuditCheck] = field(default_factory=list)

    @property
    def failed(self) -> list[AuditCheck]:
        return [c for c in self.checks if c.status == "FAIL"]

    @property
    def degraded(self) -> list[AuditCheck]:
        return [c for c in self.checks if c.status == "DEGRADED"]

    @property
    def passed(self) -> list[AuditCheck]:
        return [c for c in self.checks if c.status == "PASS"]

    @property
    def overall(self) -> str:
        if self.failed:
            return "FAIL"
        if self.degraded:
            return "DEGRADED"
        return "PASS"


class ADVISystemAuditor:
    """Read-only integration audit of the currently wired ADVI system."""

    REQUIRED_IMPORTS = (
        "advi.app",
        "advi.brain.agent",
        "advi.brain.reasoning",
        "advi.brain.planner",
        "advi.core.execution_engine",
        "advi.core.goal_verification",
        "advi.core.replanning",
        "advi.capabilities.registry",
        "advi.fallback.service",
        "advi.io.output",
    )

    def run(self, *, registry: Any | None = None, settings: Any | None = None) -> SystemAuditReport:
        report = SystemAuditReport()
        for module_name in self.REQUIRED_IMPORTS:
            try:
                importlib.import_module(module_name)
                report.checks.append(AuditCheck(f"import:{module_name}", "PASS", "importable"))
            except Exception as exc:
                report.checks.append(AuditCheck(f"import:{module_name}", "FAIL", str(exc)))

        if registry is not None:
            self._audit_registry(report, registry)

        if settings is not None:
            tts_exe = Path(settings.piper_exe)
            tts_model = Path(settings.piper_model)
            tts_ready = tts_exe.exists() and tts_model.exists() and tts_model.with_suffix(".onnx.json").exists()
            report.checks.append(
                AuditCheck("speech_output", "PASS" if tts_ready else "DEGRADED", "Piper assets ready" if tts_ready else "Piper TTS assets unavailable")
            )
            keys = bool(settings.groq_api_key or settings.gemini_api_key)
            report.checks.append(
                AuditCheck("llm_provider", "PASS" if keys else "FAIL", "at least one provider configured" if keys else "no LLM API key configured")
            )
        report.checks.append(AuditCheck("speech_input", "DEGRADED", "voice input / speech-to-text is not wired into the current production console"))
        return report

    def _audit_registry(self, report: SystemAuditReport, registry: Any) -> None:
        try:
            readiness = registry.readiness_report()
            issues = getattr(readiness, "issues", [])
            report.checks.append(
                AuditCheck("capability_readiness", "PASS" if not issues else "DEGRADED", f"{len(issues)} readiness issue(s)" if issues else "all registered capabilities are structurally ready")
            )
        except Exception as exc:
            report.checks.append(AuditCheck("capability_readiness", "FAIL", str(exc)))

        for capability in registry.list_all():
            report.checks.append(
                AuditCheck(
                    f"capability:{capability.name}",
                    "PASS" if capability.handler is not None and capability.supported_actions else "DEGRADED",
                    f"status={capability.status.value}, actions={len(capability.supported_actions)}",
                )
            )
