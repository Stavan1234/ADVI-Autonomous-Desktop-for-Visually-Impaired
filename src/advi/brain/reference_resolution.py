from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class ConversationReference:
    kind: str
    value: str
    source_id: str | None = None
    label: str = ""
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class ReferenceResolution:
    references: tuple[ConversationReference, ...] = ()
    normalized_message: str = ""
    needs_clarification: bool = False
    clarification: str | None = None

class ConversationReferenceResolver:
    def resolve(self, message: str, context: Any) -> ReferenceResolution:
        text = message.strip()
        if not text or not self._has_reference(text):
            return ReferenceResolution(normalized_message=text)
        candidates = self._candidates(context)
        if not candidates:
            return ReferenceResolution(normalized_message=text, needs_clarification=True,
                clarification="I need you to specify which item you mean; I do not have a clear recent reference.")
        compatible = [c for c in candidates if self._compatible(text, c)] or candidates
        if self._ambiguous(text, compatible):
            return ReferenceResolution(references=tuple(compatible[:4]), normalized_message=text,
                needs_clarification=True, clarification=self._clarification(compatible[:3]))
        chosen = compatible[0]
        return ReferenceResolution(references=(chosen,), normalized_message=self._substitute(text, chosen))

    def _candidates(self, context: Any) -> list[ConversationReference]:
        out=[]
        active=getattr(context,"active_task",None) or {}
        if active:
            self._task(out,active,1.0)
        for task in reversed(getattr(context,"recent_tasks",[]) or []):
            if task.get("task_id") != active.get("task_id"):
                self._task(out,task,.85)
        for result in reversed(getattr(context,"previous_action_results",[]) or []):
            action=str(result.get("action") or "")
            if action: out.append(ConversationReference("result",str(result.get("human_readable") or result.get("data") or action),action,action,.8,dict(result)))
        for research in reversed(getattr(context,"recent_research",[]) or []):
            rid=str(research.get("research_id") or "")
            if rid: out.append(ConversationReference("research",str(research.get("question") or ""),rid,str(research.get("question") or "research"),.8,{"sources":research.get("sources") or []}))
        return out

    def _task(self,out,task,confidence):
        goal=str(task.get("goal") or "")
        if goal: out.append(ConversationReference("task",goal,str(task.get("task_id") or "") or None,goal,confidence,{"status":task.get("status")}))
        entities=task.get("entities") or {}
        if isinstance(entities,dict):
            for key,value in list(entities.items())[:8]:
                if value not in (None,"",[]): out.append(ConversationReference("entity",str(value),str(key),f"{key}: {value}",min(confidence,.72),{"field":key}))

    @staticmethod
    def _has_reference(text):
        return bool(re.search(r"\b(?:that|this|the previous|the last|it)\b|\b(?:make|change|edit|update|send|open|read|delete) it\b", text, re.I))
    @staticmethod
    def _compatible(text,c):
        lower=text.lower()
        if "file" in lower: return c.kind=="entity" and c.metadata.get("field") in {"path","file","filename"}
        if "result" in lower: return c.kind=="result"
        if "source" in lower: return c.kind=="research"
        return True
    @staticmethod
    def _ambiguous(text,candidates):
        lower=text.lower()
        return ("file" in lower or "result" in lower) and len(candidates)>1
    @staticmethod
    def _substitute(text,c):
        replacement=c.value
        if c.kind=="entity" and c.metadata.get("field") in {"path","file","filename"}: pats=[r"\bthat file\b",r"\bthis file\b",r"\bthe previous file\b"]
        elif c.kind=="result": pats=[r"\bthat result\b",r"\bthis result\b",r"\bthe previous result\b",r"\bthe last one\b"]
        elif c.kind=="research": pats=[r"\bthat source\b",r"\bthis source\b",r"\bthe source\b"]
        else: pats=[r"\bthat one\b",r"\bthe previous one\b",r"\bthe last one\b",r"\bit\b"]
        for pat in pats:
            changed=re.sub(pat,replacement,text,count=1,flags=re.I)
            if changed!=text: return changed
        return text
    @staticmethod
    def _clarification(candidates): return "Which one do you mean? Recent possibilities are: "+"; ".join(c.label for c in candidates if c.label)+"."
