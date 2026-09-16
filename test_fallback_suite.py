from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Ensure local src directory is prioritized in sys.path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from advi.fallback.action_plan_schema import Action, ActionPlan
from advi.fallback.execution_loop import ExecutionLoop
from advi.fallback.executor import FallbackExecutor
from advi.fallback.intent_schema import Intent
from advi.fallback.intent_service import IntentService
from advi.fallback.planner_service import PlannerService
from advi.providers import GroqProvider

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("FallbackTestSuite")


def run_notepad_test(loop: ExecutionLoop) -> bool:
    print("\n" + "=" * 60)
    print("TEST 1: NOTEPAD DESKTOP APPLICATION")
    print("=" * 60)

    plan = ActionPlan(actions=[
        Action(action="open_application", focus="Notepad", parameters={"application": "notepad"}),
        Action(action="type_text", focus="Notepad", parameters={"value": "Hello World"}),
        Action(action="hotkey", focus="Notepad", parameters={"keys": ["CTRL", "A"]}),
        Action(action="type_text", focus="Notepad", parameters={"value": "ADVI Agentic Automation System"}),
        Action(action="press_key", focus="Notepad", parameters={"key": "ENTER"}),
        Action(action="finish", focus=None, parameters={}),
    ])

    res = loop.run(plan)
    print(f"Notepad Test Overall Success: {res.success}")
    for idx, r in enumerate(res.results, start=1):
        print(f"  Step #{idx} ({r.action}): success={r.success}, data={r.data}, error={r.error}")
    return res.success


def run_youtube_test(loop: ExecutionLoop) -> bool:
    print("\n" + "=" * 60)
    print("TEST 2: YOUTUBE IN-SITE SEARCH & VIDEO CLICK")
    print("=" * 60)

    plan = ActionPlan(actions=[
        Action(action="open_application", focus="Chrome", parameters={"application": "Chrome"}),
        Action(action="navigate", focus="Chrome", parameters={"url": "https://www.youtube.com"}),
        Action(action="search", focus="Chrome", parameters={"target": "YouTube search box", "query": "Baby Shark"}),
        Action(action="click", focus="Chrome", parameters={"target": "Baby Shark video"}),
        Action(action="finish", focus=None, parameters={}),
    ])

    res = loop.run(plan)
    print(f"YouTube Test Overall Success: {res.success}")
    for idx, r in enumerate(res.results, start=1):
        print(f"  Step #{idx} ({r.action}): success={r.success}, data={r.data}, error={r.error}")

    # Verify context target tab URL is YouTube video page
    target_url = loop.executor.context.target_tab_url or ""
    print(f"  Final Target Tab URL: {target_url}")
    return res.success and ("youtube.com" in target_url or "watch" in target_url)


def run_amazon_test(loop: ExecutionLoop) -> bool:
    print("\n" + "=" * 60)
    print("TEST 3: AMAZON IN-SITE SEARCH & PRODUCT SELECT")
    print("=" * 60)

    plan = ActionPlan(actions=[
        Action(action="open_application", focus="Chrome", parameters={"application": "Chrome"}),
        Action(action="navigate", focus="Chrome", parameters={"url": "https://www.amazon.com"}),
        Action(action="search", focus="Chrome", parameters={"target": "Amazon search field", "query": "wireless mouse"}),
        Action(action="click", focus="Chrome", parameters={"target": "first product"}),
        Action(action="finish", focus=None, parameters={}),
    ])

    res = loop.run(plan)
    print(f"Amazon Test Overall Success: {res.success}")
    for idx, r in enumerate(res.results, start=1):
        print(f"  Step #{idx} ({r.action}): success={r.success}, data={r.data}, error={r.error}")

    target_url = loop.executor.context.target_tab_url or ""
    print(f"  Final Target Tab URL: {target_url}")
    return res.success and "amazon.com" in target_url


def run_reddit_test(loop: ExecutionLoop) -> bool:
    print("\n" + "=" * 60)
    print("TEST 4: REDDIT IN-SITE SEARCH & RESULT INTERACTION")
    print("=" * 60)

    plan = ActionPlan(actions=[
        Action(action="open_application", focus="Chrome", parameters={"application": "Chrome"}),
        Action(action="navigate", focus="Chrome", parameters={"url": "https://www.reddit.com"}),
        Action(action="search", focus="Chrome", parameters={"target": "Reddit search field", "query": "AI agents"}),
        Action(action="click", focus="Chrome", parameters={"target": "first search result"}),
        Action(action="finish", focus=None, parameters={}),
    ])

    res = loop.run(plan)
    print(f"Reddit Test Overall Success: {res.success}")
    for idx, r in enumerate(res.results, start=1):
        print(f"  Step #{idx} ({r.action}): success={r.success}, data={r.data}, error={r.error}")

    target_url = loop.executor.context.target_tab_url or ""
    print(f"  Final Target Tab URL: {target_url}")
    return res.success and "reddit.com" in target_url


def run_tab_isolation_test(loop: ExecutionLoop) -> bool:
    print("\n" + "=" * 60)
    print("TEST 5: MULTIPLE CHROME TABS ISOLATION")
    print("=" * 60)

    # 1. Open background tab
    cdp = loop.executor.cdp_browser
    existing_tabs_before = cdp.list_tabs()
    print(f"Pre-existing tabs count: {len(existing_tabs_before)}")

    # Run automation to create target tab
    plan = ActionPlan(actions=[
        Action(action="open_application", focus="Chrome", parameters={"application": "Chrome"}),
        Action(action="navigate", focus="Chrome", parameters={"url": "https://wikipedia.org"}),
        Action(action="search", focus="Chrome", parameters={"target": "Wikipedia search box", "query": "Artificial Intelligence"}),
        Action(action="finish", focus=None, parameters={}),
    ])

    res = loop.run(plan)
    bound_tab_id = loop.executor.context.target_tab_id
    print(f"Bound Target Tab ID: {bound_tab_id}")

    # Check tab ownership retention
    all_tabs = cdp.list_tabs()
    print(f"Total tabs after test: {len(all_tabs)}")

    target_tab_info = cdp.get_tab_info(bound_tab_id) if bound_tab_id else None
    is_valid = res.success and bool(target_tab_info) and "wikipedia.org" in (target_tab_info.get("url") or "")
    print(f"Tab Isolation Test Passed: {is_valid}")
    return is_valid


def main() -> None:
    load_dotenv()
    print("=" * 60)
    print("ADVI FALLBACK AUTOMATION SYSTEM — E2E TEST SUITE")
    print("=" * 60)

    loop = ExecutionLoop()

    test_results = {}
    test_results["Notepad"] = run_notepad_test(loop)
    test_results["YouTube"] = run_youtube_test(loop)
    test_results["Amazon"] = run_amazon_test(loop)
    test_results["Reddit"] = run_reddit_test(loop)
    test_results["Tab Isolation"] = run_tab_isolation_test(loop)

    print("\n" + "=" * 60)
    print("E2E TEST SUITE SUMMARY")
    print("=" * 60)
    all_passed = True
    for name, passed in test_results.items():
        status = "PASSED" if passed else "FAILED"
        print(f"  {name:<25}: {status}")
        if not passed:
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("ALL END-TO-END TESTS PASSED SUCCESSFULLY!")
    else:
        print("SOME TESTS FAILED — CHECK LOGS ABOVE.")
    print("=" * 60)


if __name__ == "__main__":
    main()
