from advi.brain.context import AgentContext
from advi.brain.reference_resolution import ConversationReferenceResolver

def make_context(active=None, recent=None, results=None):
    return AgentContext(current_message="", active_task=active, recent_tasks=recent or [], previous_action_results=results or [])

def test_resolves_file_reference():
    c=make_context({"task_id":"t1","goal":"modify report","entities":{"path":"/tmp/report.txt"}})
    r=ConversationReferenceResolver().resolve("append this file",c)
    assert not r.needs_clarification and "/tmp/report.txt" in r.normalized_message

def test_resolves_result_reference():
    c=make_context(results=[{"action":"read_file","human_readable":"report contents","success":True}])
    r=ConversationReferenceResolver().resolve("use that result",c)
    assert not r.needs_clarification and "report contents" in r.normalized_message

def test_asks_for_ambiguous_file():
    c=make_context({"task_id":"t1","goal":"compare","entities":{"path":"a.txt","file":"b.txt"}})
    assert ConversationReferenceResolver().resolve("open that file",c).needs_clarification

def test_plain_message_unchanged():
    r=ConversationReferenceResolver().resolve("hello there",make_context())
    assert r.normalized_message == "hello there" and not r.needs_clarification
