from __future__ import annotations

import logging
import os
import subprocess
import time
import urllib.parse
from pathlib import Path
from typing import Any

from advi.core.action_plan import Action, ExecutionResult
from advi.core.research_quality import rank_and_dedupe_sources
from advi.capabilities.desktop.context import DesktopContext
from .cdp import CDPBrowser

logger = logging.getLogger(__name__)


class BrowserCapability:
    """
    Browser Automation Capability.
    Directly controls Chrome via Chrome DevTools Protocol (CDP).
    Handles navigation, in-page search, clicking DOM elements, and tab lifecycle.
    """

    SUPPORTED_ACTIONS = {
        "navigate",
        "search",
        "click_web_element",
        "read_web_page",
        "research_web",
        "research_web_multi",
    }

    def __init__(
        self,
        context: DesktopContext | None = None,
        cdp_port: int = 9222,
    ) -> None:
        self.context = context or DesktopContext()
        self.cdp_port = cdp_port
        self.cdp = CDPBrowser(port=cdp_port)

    def close(self) -> None:
        """Stop Chrome only when this capability launched its dedicated process."""
        pid = self.context.chrome_process_id
        self.context.chrome_process_id = None
        if not pid:
            return
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True)
            else:
                os.kill(pid, 15)
        except (OSError, ValueError) as exc:
            logger.warning("Could not stop ADVI-launched Chrome process %s: %s", pid, exc)

    def execute(self, action: Action) -> ExecutionResult:
        handler = getattr(self, f"_execute_{action.action}", None)
        if handler is None:
            return ExecutionResult(
                action=action.action,
                success=False,
                error=f"Unsupported browser action: {action.action}",
            )

        try:
            # Ensure Chrome is running and tab is ready before executing browser action
            if not self._ensure_chrome_running():
                return ExecutionResult(
                    action=action.action,
                    success=False,
                    error="Failed to launch or attach to Chrome via CDP.",
                )
            return handler(action)
        except Exception as exc:
            logger.exception("Browser action execution failed: %s", action.action)
            return ExecutionResult(
                action=action.action,
                success=False,
                error=str(exc),
            )

    def _ensure_chrome_running(self) -> bool:
        """Verify Chrome is running with remote debugging, launch if needed, and bind target tab."""
        tabs = self.cdp.list_tabs()
        if tabs:
            if not self.context.target_tab_id:
                # Use first active page tab or create new
                target_tab = next((t for t in tabs if t.get("type") == "page"), None)
                if target_tab:
                    self.context.set_target_tab(
                        tab_id=target_tab["id"],
                        url=target_tab.get("url"),
                        title=target_tab.get("title"),
                    )
            return True

        # Launch Chrome with CDP
        possible_paths = [
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        ]

        chrome_exe = next((p for p in possible_paths if p.exists()), None)
        if not chrome_exe:
            logger.warning("Chrome executable not found in standard paths.")
            return False

        profile_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "ADVI" / "ChromeProfile"
        profile_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(chrome_exe),
            f"--remote-debugging-port={self.cdp_port}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank",
        ]

        try:
            proc = subprocess.Popen(cmd, creationflags=subprocess.DETACHED_PROCESS if os.name == "nt" else 0)
            self.context.chrome_process_id = proc.pid
            time.sleep(1.5)

            tabs = self.cdp.list_tabs()
            if tabs:
                self.context.set_target_tab(
                    tab_id=tabs[0]["id"],
                    url=tabs[0].get("url"),
                    title=tabs[0].get("title"),
                )
                return True
        except Exception as exc:
            logger.exception("Failed to launch Chrome with CDP: %s", exc)

        return False

    def _execute_navigate(self, action: Action) -> ExecutionResult:
        url = action.parameters.get("url") or action.target or ""
        if not url:
            return ExecutionResult(
                action=action.action,
                success=False,
                error="No URL specified for navigation.",
            )

        clean_url = str(url).strip()
        if not clean_url.startswith(("http://", "https://")):
            clean_url = f"https://{clean_url}"

        tab_id = self.context.target_tab_id
        if not tab_id:
            tabs = self.cdp.list_tabs()
            if tabs:
                tab_id = tabs[0]["id"]
                self.context.set_target_tab(tab_id)

        if not tab_id:
            return ExecutionResult(
                action=action.action,
                success=False,
                error="No active Chrome tab found to navigate.",
            )

        success = self.cdp.navigate_tab(tab_id=tab_id, url=clean_url)
        if success:
            get_tab_info = getattr(self.cdp, "get_tab_info", None)
            actual = (get_tab_info(tab_id) if get_tab_info else {}) or {}
            actual_url = actual.get("url") or clean_url
            actual_title = actual.get("title")
            self.context.target_tab_url = actual_url
            if actual_title is not None:
                self.context.target_tab_title = actual_title
            return ExecutionResult(
                action=action.action,
                success=True,
                data=actual_url,
                human_readable=f"Navigated browser to {actual_url}.",
                metadata={
                    "current_url": actual_url,
                    "expected_url": clean_url,
                    "tab_title": actual_title,
                    "cdp_port": self.cdp_port,
                    "tab_id": tab_id,
                },
            )

        return ExecutionResult(
            action=action.action,
            success=False,
            error=f"Failed to navigate to {clean_url}.",
        )

    def _execute_search(self, action: Action) -> ExecutionResult:
        query = action.parameters.get("query") or action.parameters.get("value") or ""
        target_site = action.parameters.get("target") or action.target or ""

        if not query:
            return ExecutionResult(
                action=action.action,
                success=False,
                error="No search query specified.",
            )

        tab_id = self.context.target_tab_id
        if not tab_id:
            return ExecutionResult(
                action=action.action,
                success=False,
                error="No active Chrome tab available for search.",
            )

        # In-page search if on a specific site (e.g. YouTube, Amazon, Wikipedia)
        current_url = self.context.target_tab_url or ""
        search_selectors = [
            "input[name='search_query']",  # YouTube
            "input[name='q']",             # Google / generic
            "#twotabsearchtextbox",        # Amazon
            "input[type='search']",        # HTML5 search
            "input[name='search']",        # Wikipedia / mediawiki
            "input[placeholder*='search' i]",
        ]

        typed = False
        for selector in search_selectors:
            try:
                res = self.cdp.evaluate_script(
                    tab_id,
                    f"""
                    (() => {{
                        const el = document.querySelector('{selector}');
                        if (el) {{
                            el.focus();
                            el.value = {repr(str(query))};
                            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            if (el.form) {{
                                el.form.submit();
                            }} else {{
                                const event = new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }});
                                el.dispatchEvent(event);
                            }}
                            return true;
                        }}
                        return false;
                    }})()
                    """,
                )
                if res and res.get("value") is True:
                    typed = True
                    time.sleep(1.0)
                    break
            except Exception:
                continue

        if not typed:
            # Fallback: navigate directly to a Google search URL
            encoded_query = urllib.parse.quote_plus(str(query))
            search_url = f"https://www.google.com/search?q={encoded_query}"
            nav_success = self.cdp.navigate_tab(tab_id=tab_id, url=search_url)
            if not nav_success:
                return ExecutionResult(
                    action=action.action,
                    success=False,
                    error=f"In-page search failed and fallback navigation to Google also failed for query '{query}'.",
                )
            get_tab_info = getattr(self.cdp, "get_tab_info", None)
            info = (get_tab_info(tab_id) if get_tab_info else {}) or {}
            actual_url = info.get("url") or search_url
            self.context.target_tab_url = actual_url
            return ExecutionResult(
                action=action.action,
                success=True,
                data=str(query),
                human_readable=f"Searched Google for '{query}'.",
                metadata={
                    "query": str(query),
                    "method": "google_fallback",
                    "search_url": search_url,
                    "current_url": actual_url,
                    "cdp_port": self.cdp_port,
                    "tab_id": tab_id,
                },
            )

        get_tab_info = getattr(self.cdp, "get_tab_info", None)
        info = (get_tab_info(tab_id) if get_tab_info else {}) or {}
        actual_url = info.get("url") or self.context.target_tab_url
        self.context.target_tab_url = actual_url
        return ExecutionResult(
            action=action.action,
            success=True,
            data=str(query),
            human_readable=f"Searched for '{query}' on page.",
            metadata={
                "query": str(query),
                "method": "in_page",
                "current_url": actual_url,
                "cdp_port": self.cdp_port,
                "tab_id": tab_id,
            },
        )

    def _execute_click_web_element(self, action: Action) -> ExecutionResult:
        selector = action.parameters.get("selector") or action.target or ""
        tab_id = self.context.target_tab_id
        if not tab_id or not selector:
            return ExecutionResult(
                action=action.action,
                success=False,
                error="Tab ID or selector missing.",
            )

        res = self.cdp.evaluate_script(
            tab_id,
            f"""
            (() => {{
                const el = document.querySelector({repr(str(selector))});
                if (!el) return {{success: false, reason: "element_not_found"}};
                const before = {{url: window.location.href, title: document.title}};
                el.scrollIntoView({{block: "center"}});
                el.click();
                return {{success: true, before}};
            }})()
            """,
        )

        raw_value = res.get("value") if isinstance(res, dict) else None
        if isinstance(raw_value, dict):
            success = raw_value.get("success") is True
            before_state = raw_value.get("before", {}) or {}
            reason = raw_value.get("reason", "click_failed")
        else:
            # Preserve compatibility with older CDP adapters that returned {value: True}.
            success = raw_value is True
            before_state = {"url": self.context.target_tab_url, "title": self.context.target_tab_title}
            reason = "click_failed"
        if not success:
            return ExecutionResult(
                action=action.action, success=False, data=selector,
                error=f"Could not click web element '{selector}': {reason}",
                metadata={"selector": selector, "cdp_port": self.cdp_port, "tab_id": tab_id},
            )

        time.sleep(0.5)
        get_tab_info = getattr(self.cdp, "get_tab_info", None)
        after = (get_tab_info(tab_id) if get_tab_info else {}) or {}
        actual_url = after.get("url")
        actual_title = after.get("title")
        if actual_url:
            self.context.target_tab_url = actual_url
        if actual_title is not None:
            self.context.target_tab_title = actual_title
        return ExecutionResult(
            action=action.action,
            success=True,
            data=selector,
            human_readable=f"Clicked web element '{selector}'.",
            metadata={
                "selector": selector,
                "before_url": before_state.get("url"),
                "current_url": actual_url,
                "tab_title": actual_title,
                "cdp_port": self.cdp_port,
                "tab_id": tab_id,
            },
        )


    def _execute_research_web(self, action: Action) -> ExecutionResult:
        """Run a bounded search -> select -> navigate -> read workflow.

        This is intentionally deterministic: the workflow uses the browser's
        existing primitives and chooses a result by transparent text/URL scoring.
        It does not ask an LLM to invent a selector or claim that a source was opened.
        """
        query = str(action.parameters.get("query") or "").strip()
        target = str(
            action.parameters.get("target")
            or action.parameters.get("site")
            or action.target
            or ""
        ).strip()
        max_chars_raw = action.parameters.get("max_chars", 4000)
        try:
            max_chars = max(500, min(12000, int(max_chars_raw)))
        except (TypeError, ValueError):
            max_chars = 4000

        if not query:
            return ExecutionResult(
                action=action.action, success=False, error="No web research query specified."
            )

        tab_id = self.context.target_tab_id
        if not tab_id:
            tabs = self.cdp.list_tabs()
            if tabs:
                tab_id = tabs[0]["id"]
                self.context.set_target_tab(tab_id)
        if not tab_id:
            return ExecutionResult(
                action=action.action, success=False, error="No active Chrome tab available for web research."
            )

        search_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"
        if not self.cdp.navigate_tab(tab_id=tab_id, url=search_url):
            return ExecutionResult(
                action=action.action, success=False,
                error=f"Could not open search results for '{query}'."
            )

        time.sleep(0.8)
        self.context.target_tab_url = search_url

        try:
            result = self.cdp.evaluate_script(
                tab_id,
                rf"""
                (() => {{
                    const target = {target!r}.toLowerCase();
                    const tokens = target.split(/[^a-z0-9]+/).filter(Boolean);
                    const anchors = Array.from(document.querySelectorAll('a[href]'));
                    const candidates = anchors.map(a => ({{
                        text: (a.innerText || a.textContent || '').trim().replace(/\s+/g, ' '),
                        href: a.href || ''
                    }})).filter(x => x.text && /^https?:/i.test(x.href));
                    const filtered = candidates.filter(x =>
                        !/^(?:https?:\/\/)?(?:www\.)?google\./i.test(x.href) &&
                        !/accounts\.google\.com|support\.google\.com|policies\.google\.com/i.test(x.href)
                    );
                    const scored = filtered.map(x => {{
                        const hay = (x.text + ' ' + x.href).toLowerCase();
                        let score = 0;
                        for (const token of tokens) if (hay.includes(token)) score += 2;
                        if (tokens.length && tokens.every(t => hay.includes(t))) score += 4;
                        return {{...x, score}};
                    }}).sort((a,b) => b.score - a.score);
                    return {{candidates: scored.slice(0, 10)}};
                }})()
                """,
            )
        except Exception as exc:
            return ExecutionResult(
                action=action.action, success=False, error=f"Could not inspect search results: {exc}"
            )

        raw = result.get("value") if isinstance(result, dict) else result
        candidates = raw.get("candidates", []) if isinstance(raw, dict) else []
        if not candidates:
            return ExecutionResult(
                action=action.action, success=False, data=str(query),
                error="Search completed but no usable result links were found.",
                metadata={"query": query, "search_url": search_url, "tab_id": tab_id},
            )

        selected = candidates[0]
        href = str(selected.get("href") or "").strip()
        if not href:
            return ExecutionResult(
                action=action.action, success=False, error="Selected search result did not contain a URL."
            )

        if not self.cdp.navigate_tab(tab_id=tab_id, url=href):
            return ExecutionResult(
                action=action.action, success=False,
                error=f"Could not open selected search result: {href}",
                metadata={"query": query, "selected_result": selected, "tab_id": tab_id},
            )
        time.sleep(0.8)

        get_tab_info = getattr(self.cdp, "get_tab_info", None)
        info = (get_tab_info(tab_id) if get_tab_info else {}) or {}
        current_url = info.get("url") or href
        title = info.get("title") or selected.get("text")
        self.context.target_tab_url = current_url
        if title is not None:
            self.context.target_tab_title = title

        try:
            body = self.cdp.evaluate_script(
                tab_id,
                f"document.body ? document.body.innerText.substring(0, {max_chars}) : ''",
            )
            text = body.get("value", "") if isinstance(body, dict) else ""
        except Exception as exc:
            return ExecutionResult(
                action=action.action, success=False,
                error=f"Opened the result but could not read the page: {exc}",
                metadata={"query": query, "selected_result": selected, "current_url": current_url, "tab_id": tab_id},
            )

        if not isinstance(text, str) or not text.strip():
            return ExecutionResult(
                action=action.action, success=True, data="",
                human_readable=f"Opened {current_url}, but the page contained no readable text.",
                metadata={
                    "query": query, "selected_result": selected, "current_url": current_url,
                    "tab_title": title, "content_available": False, "tab_id": tab_id,
                },
            )

        return ExecutionResult(
            action=action.action, success=True, data=text,
            human_readable=f"Opened and read {title or current_url}.",
            metadata={
                "query": query, "search_url": search_url, "selected_result": selected,
                "current_url": current_url, "tab_title": title,
                "content_available": True, "content_length": len(text),
                "tab_id": tab_id, "cdp_port": self.cdp_port,
            },
        )


    def _execute_research_web_multi(self, action: Action) -> ExecutionResult:
        """Run bounded multi-source web research with deterministic evidence aggregation.

        The workflow is intentionally finite: collect a small number of search-result
        candidates, optionally inspect one additional results page, open each selected
        source, and capture a bounded text excerpt. No autonomous crawling or LLM
        selector generation is performed here.
        """
        query = str(action.parameters.get("query") or "").strip()
        target = str(
            action.parameters.get("target")
            or action.parameters.get("site")
            or action.target
            or ""
        ).strip()
        try:
            max_sources = max(1, min(5, int(action.parameters.get("max_sources", 3))))
        except (TypeError, ValueError):
            max_sources = 3
        try:
            pages = max(1, min(2, int(action.parameters.get("pages", 1))))
        except (TypeError, ValueError):
            pages = 1
        try:
            max_chars = max(500, min(8000, int(action.parameters.get("max_chars", 2500))))
        except (TypeError, ValueError):
            max_chars = 2500

        if not query:
            return ExecutionResult(action=action.action, success=False, error="No multi-source web research query specified.")

        tab_id = self.context.target_tab_id
        if not tab_id:
            tabs = self.cdp.list_tabs()
            if tabs:
                tab_id = tabs[0]["id"]
                self.context.set_target_tab(tab_id)
        if not tab_id:
            return ExecutionResult(action=action.action, success=False, error="No active Chrome tab available for multi-source research.")

        candidates: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        search_pages: list[str] = []

        for page_index in range(pages):
            start = page_index * 10
            search_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"
            if start:
                search_url += f"&start={start}"
            search_pages.append(search_url)
            if not self.cdp.navigate_tab(tab_id=tab_id, url=search_url):
                if not candidates:
                    return ExecutionResult(action=action.action, success=False, error=f"Could not open search results for '{query}'.")
                break
            time.sleep(0.5)
            try:
                result = self.cdp.evaluate_script(
                    tab_id,
                    rf"""
                    (() => {{
                        const target = {target!r}.toLowerCase();
                        const tokens = target.split(/[^a-z0-9]+/).filter(Boolean);
                        const anchors = Array.from(document.querySelectorAll('a[href]'));
                        const items = anchors.map(a => ({{
                            text: (a.innerText || a.textContent || '').trim().replace(/\\s+/g, ' '),
                            href: a.href || ''
                        }})).filter(x => x.text && /^https?:/i.test(x.href));
                        const filtered = items.filter(x =>
                            !/^(?:https?:\\/\\/)?(?:www\\.)?google\\./i.test(x.href) &&
                            !/accounts\\.google\\.com|support\\.google\\.com|policies\\.google\\.com/i.test(x.href)
                        );
                        const scored = filtered.map(x => {{
                            const hay = (x.text + ' ' + x.href).toLowerCase();
                            let score = 0;
                            for (const token of tokens) if (hay.includes(token)) score += 2;
                            if (tokens.length && tokens.every(t => hay.includes(t))) score += 4;
                            return {{...x, score}};
                        }}).sort((a,b) => b.score - a.score);
                        return {{candidates: scored.slice(0, 20)}};
                    }})()
                    """,
                )
            except Exception:
                continue
            raw = result.get("value") if isinstance(result, dict) else result
            page_candidates = raw.get("candidates", []) if isinstance(raw, dict) else []
            for candidate in page_candidates:
                href = str(candidate.get("href") or "").strip()
                if not href or href in seen_urls:
                    continue
                try:
                    domain = urllib.parse.urlparse(href).netloc.lower().split(":", 1)[0]
                except Exception:
                    domain = ""
                canonical = href.split("#", 1)[0]
                if canonical in seen_urls:
                    continue
                seen_urls.add(canonical)
                candidates.append({
                    "text": str(candidate.get("text") or ""),
                    "href": href,
                    "score": int(candidate.get("score") or 0),
                    "domain": domain,
                })
                if len(candidates) >= max_sources * 3:
                    break
            if len(candidates) >= max_sources * 3:
                break

        if not candidates:
            return ExecutionResult(
                action=action.action,
                success=False,
                data=str(query),
                error="Search completed but no diverse usable source links were found.",
                metadata={"query": query, "search_pages": search_pages, "tab_id": tab_id},
            )

        sources: list[dict[str, Any]] = []
        # Inspect a bounded candidate pool before selecting final evidence so that
        # freshness, content quality, duplicates, and domain diversity can all
        # influence the final source set.
        for source in candidates[: max_sources * 3]:
            href = source["href"]
            if not self.cdp.navigate_tab(tab_id=tab_id, url=href):
                sources.append({**source, "opened": False, "readable": False, "error": "navigation_failed"})
                continue
            time.sleep(0.5)
            get_tab_info = getattr(self.cdp, "get_tab_info", None)
            info = (get_tab_info(tab_id) if get_tab_info else {}) or {}
            current_url = info.get("url") or href
            title = info.get("title") or source["text"]
            published_at = None
            try:
                meta = self.cdp.evaluate_script(
                    tab_id,
                    """(() => ({
                        published_at: document.querySelector('meta[property=\"article:published_time\"], meta[name=\"date\"], time[datetime]')?.content || document.querySelector('time[datetime]')?.getAttribute('datetime') || null,
                        modified_at: document.querySelector('meta[property=\"article:modified_time\"], meta[name=\"lastmod\"]')?.content || null
                    }))()""",
                )
                meta_value = meta.get("value", {}) if isinstance(meta, dict) else {}
                if isinstance(meta_value, dict):
                    published_at = meta_value.get("published_at") or meta_value.get("modified_at")
            except Exception:
                published_at = None
            try:
                body = self.cdp.evaluate_script(
                    tab_id,
                    f"document.body ? document.body.innerText.substring(0, {max_chars}) : ''",
                )
                text = body.get("value", "") if isinstance(body, dict) else ""
            except Exception as exc:
                text = ""
                error = str(exc)
            else:
                error = None
            readable = isinstance(text, str) and bool(text.strip())
            sources.append({
                **source,
                "opened": True,
                "readable": readable,
                "url": current_url,
                "title": title,
                "content": text if isinstance(text, str) else "",
                "content_length": len(text) if isinstance(text, str) else 0,
                "published_at": published_at,
                **({"error": error} if error else {}),
            })

        readable_sources = rank_and_dedupe_sources(
            sources, query=query, max_sources=max_sources
        )
        for idx, item in enumerate(readable_sources, start=1):
            item["index"] = idx

        readable_count = len(readable_sources)
        if readable_count == 0:
            return ExecutionResult(
                action=action.action,
                success=False,
                data=sources,
                error="Sources were selected but none produced readable, sufficiently substantive page content.",
                metadata={
                    "query": query,
                    "search_pages": search_pages,
                    "candidate_count": len(candidates),
                    "sources": sources,
                    "source_count": len(sources),
                    "readable_source_count": 0,
                    "tab_id": tab_id,
                    "cdp_port": self.cdp_port,
                },
            )

        self.context.target_tab_url = readable_sources[-1].get("url") or readable_sources[-1]["href"]
        self.context.target_tab_title = readable_sources[-1].get("title") or self.context.target_tab_title
        summary = "\n\n".join(
            f"[S{idx}] {item.get('title') or item.get('url')}\n{item.get('content', '')}"
            for idx, item in enumerate(readable_sources, start=1)
        )
        return ExecutionResult(
            action=action.action,
            success=True,
            data=summary,
            human_readable=f"Collected readable evidence from {readable_count} web source{'s' if readable_count != 1 else ''}.",
            metadata={
                "query": query,
                "target": target,
                "search_pages": search_pages,
                "sources": readable_sources,
                "source_count": len(readable_sources),
                "candidate_count": len(candidates),
                "readable_source_count": readable_count,
                "tab_id": tab_id,
                "cdp_port": self.cdp_port,
                "bounded": True,
            },
        )

    def _execute_read_web_page(self, action: Action) -> ExecutionResult:
        tab_id = self.context.target_tab_id
        if not tab_id:
            return ExecutionResult(action=action.action, success=False, error="No active tab.")

        res = self.cdp.evaluate_script(
            tab_id,
            "document.body.innerText.substring(0, 4000)",
        )
        text = res.get("value", "") if res else ""
        get_tab_info = getattr(self.cdp, "get_tab_info", None)
        info = (get_tab_info(tab_id) if get_tab_info else {}) or {}
        current_url = info.get("url") or self.context.target_tab_url
        title = info.get("title") or self.context.target_tab_title
        if current_url:
            self.context.target_tab_url = current_url
        if title is not None:
            self.context.target_tab_title = title
        return ExecutionResult(
            action=action.action,
            success=isinstance(text, str),
            data=text,
            human_readable=f"Extracted {len(text)} characters from page.",
            metadata={
                "tab_id": tab_id,
                "cdp_port": self.cdp_port,
                "current_url": current_url,
                "tab_title": title,
                "length": len(text) if isinstance(text, str) else 0,
                "page_text_available": bool(text),
            },
        )
