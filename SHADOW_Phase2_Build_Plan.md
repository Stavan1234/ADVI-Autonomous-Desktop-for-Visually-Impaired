# S.H.A.D.O.W. — Phase 2 Build Plan
*File reading, smart screen understanding, deep app control, browser control.*
*Extends the working MVP — same tool-dispatcher pattern, same "verify, don't assume" discipline
that fixed the app-open bug. Do these roughly in order; each one is genuinely independent, so
skipping around is fine, but the OCR tier especially benefits from app control already existing.*

---

## 0. The principle that governs every phase below

Your app-index fix taught the real lesson here: **the model will confidently claim success anywhere you haven't built a tool that checks the truth.** Every phase below follows the same shape —

1. Try the cheapest, most reliable method first (usually a system API, not the model).
2. Only escalate to something slower/more expensive (OCR, then vision model) when the cheap method genuinely can't answer.
3. Never report success without a real check behind it.

---

## Phase 1 — File Reading (do this first, it's the easiest win)

You already have `fs_index` resolving paths. This phase just adds the "open and understand it" half.

```bash
pip install pypdf python-docx
```
```python
# src/file_reader.py
import os
from pypdf import PdfReader
from docx import Document as DocxDocument

def read_file_content(path: str, max_chars: int = 8000) -> str:
    """Extracts text from txt/pdf/docx. Caps length so it fits the model's context —
    for a genuinely huge document you'd want chunking, but for a personal assistant's
    typical use (a letter, a short report) this covers it honestly."""
    ext = os.path.splitext(path)[1].lower()

    if ext == ".txt":
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()[:max_chars]

    elif ext == ".pdf":
        reader = PdfReader(path)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return text[:max_chars]

    elif ext == ".docx":
        doc = DocxDocument(path)
        text = "\n".join(p.text for p in doc.paragraphs)
        return text[:max_chars]

    else:
        return f"[Unsupported file type: {ext}]"
```

Add as a tool:
```python
{
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read and answer questions about a text/PDF/Word file",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path or name"},
                "question": {"type": "string", "description": "What to answer about the file (optional — summarize if omitted)"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
},
```
Dispatcher branch — resolve the path exactly like your other file tools, then just pass the extracted text back as the tool result (let the model answer the question in its normal response, don't make a second Groq call inside the tool):
```python
elif fn_name == "read_file":
    path = sanitise_path(fn_args["path"])
    content = read_file_content(path)
    return json.dumps({"success": True, "content": content})
```

**Milestone check:** "what does that PDF on my desktop say about X" resolves the path, extracts text, and the model answers correctly from the tool result.

---

## Phase 2 — Smart OCR: tiered, so you're not paying vision-model cost for plain text

This is the part worth designing carefully, because "very very smart OCR" and "efficient" are in tension if you reach for a vision model on every screen-read. The fix is a **three-tier escalation**, cheapest first:

```
Tier 0: Accessibility tree (pywinauto/UIA)  →  free, instant, exact text
Tier 1: Local OCR (Tesseract) on a screenshot →  free, fast, raw text only
Tier 2: Groq vision model (qwen/qwen3.6-27b) →  costs tokens, understands layout/images/icons
```
Escalate only when the tier below genuinely fails — don't skip straight to Tier 2 out of convenience.

```bash
pip install pytesseract pillow
# Also install Tesseract OCR itself (the actual engine, not just the Python wrapper):
# https://github.com/UB-Mannheim/tesseract/wiki — Windows installer, then add to PATH
```

```python
# src/screen_reader.py
import pytesseract
from PIL import ImageGrab
import base64, io
from groq import Groq
import os

client = Groq(api_key=os.environ["GROQ_API_KEY"])


def capture_screen(region: tuple | None = None):
    return ImageGrab.grab(bbox=region)  # region=(x1,y1,x2,y2), or None for full screen


def tier1_ocr(image) -> str:
    """Local, free, fast — but only extracts raw text, no layout/visual understanding."""
    return pytesseract.image_to_string(image).strip()


def tier2_vision(image, question: str) -> str:
    """Escalation only — costs real tokens, but genuinely understands layout, icons,
    charts, anything OCR's plain-text extraction can't capture."""
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    response = client.chat.completions.create(
        model="qwen/qwen3.6-27b",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ],
        }],
    )
    return response.choices[0].message.content


def read_screen(question: str, region: tuple | None = None) -> str:
    """The full tiered pipeline. Tier 0 (accessibility tree) is attempted separately
    in app_control.py before this is ever called — this function is the fallback path."""
    image = capture_screen(region)
    raw_text = tier1_ocr(image)

    if not raw_text:
        # OCR found literally no text — this is a genuinely visual question
        # (an icon, a photo, a chart), so escalate straight to Tier 2.
        return tier2_vision(image, question)

    # We have text — answer using the cheap text model, not the vision model.
    # This is the actual "smart" part: don't pay image-token prices for a
    # question a plain-text answer already solves.
    from brain import chat
    reply = chat([
        {"role": "system", "content": "Answer based only on this text extracted from the user's screen."},
        {"role": "user", "content": f"Screen text:\n{raw_text}\n\nQuestion: {question}"},
    ])
    return reply.content
```

Wire the Tier 0 attempt (accessibility tree of the foreground window) before calling `read_screen` at all — covered in Phase 3 below, since it reuses the same `pywinauto` connection you'll build for app control anyway.

**Milestone check:** ask "what does the error message on screen say" with a plain text dialog open — should resolve via Tier 1 (OCR) and never touch the vision model. Then ask "what's in this photo I have open" with an image viewer open — should correctly fall through to Tier 2, since OCR finds no text.

---

## Phase 3 — Deep Application Control (typing/clicking inside apps, not just launching)

Your `app_index.py` already resolves and launches apps. This phase adds *acting inside* one once it's open.

```bash
pip install pywinauto
```
```python
# src/app_control.py
from pywinauto import Desktop
import win32gui


def get_foreground_window_title() -> str:
    """The safety check from the master spec — know what has focus before acting on it."""
    hwnd = win32gui.GetForegroundWindow()
    return win32gui.GetWindowText(hwnd)


def get_foreground_accessibility_text() -> str | None:
    """Tier 0 for smart OCR — read the actual UIA tree of whatever's focused,
    which is instant and exact when it works, unlike a screenshot."""
    try:
        window = Desktop(backend="uia").window(active_only=True)
        texts = [c.window_text() for c in window.descendants() if c.window_text().strip()]
        return "\n".join(texts) if texts else None
    except Exception:
        return None


def type_into_foreground(text: str) -> dict:
    """Sends keystrokes to whatever currently has focus. Simple and general — works
    across almost any app without per-app-specific automation code, at the cost of
    being less precise than targeting a specific control by name."""
    try:
        window = Desktop(backend="uia").window(active_only=True)
        window.type_keys(text, with_spaces=True, with_tabs=True, with_newlines=True)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def click_control(name: str) -> dict:
    """Finds a control by its visible name in the foreground window and clicks it —
    this is what makes 'click Send' or 'click Save' possible without coordinates."""
    try:
        window = Desktop(backend="uia").window(active_only=True)
        control = window.child_window(title_re=f".*{name}.*", control_type="Button")
        control.click_input()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": f"Couldn't find a control matching '{name}': {e}"}
```

Add two tools:
```python
{
    "type": "function",
    "function": {
        "name": "type_into_app",
        "description": "Type text into whatever application currently has focus",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
    },
},
{
    "type": "function",
    "function": {
        "name": "click_ui_button",
        "description": "Click a button by its visible label in the currently focused application",
        "parameters": {
            "type": "object",
            "properties": {"button_name": {"type": "string"}},
            "required": ["button_name"],
            "additionalProperties": False,
        },
    },
},
```

**This directly fixes the "write a poem inside Word" gap from your MVP test** — before, the model correctly refused (an honest answer, better than a false claim, but not what you wanted); now `type_into_app` actually sends the text into whatever's focused.

**One safety addition, matching your foreground-window design principle:** before calling `type_into_foreground`, confirm the foreground window is actually the one the user expects (`get_foreground_window_title()`), and if it's ambiguous, ask rather than typing into the wrong place.

**Milestone check:** "open notepad and write a haiku" should launch (existing `app_index`), then genuinely type the haiku into the actual Notepad window — verify by reading it back with `get_foreground_accessibility_text()` afterward, not just assuming the keystrokes landed.

---

## Phase 4 — Browser Control

```bash
pip install playwright
playwright install chromium
```

```python
# src/browser_control.py
from playwright.sync_api import sync_playwright

_playwright = None
_browser = None
_page = None


def get_page():
    """Reuses one persistent browser session across the conversation — matches the
    session-ledger principle from earlier: don't silently spawn a fresh browser for
    every request, reuse what's already open unless the user wants a new one."""
    global _playwright, _browser, _page
    if _page is None:
        _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch(headless=False)
        _page = _browser.new_page()
    return _page


def navigate(url: str) -> dict:
    page = get_page()
    try:
        page.goto(url, timeout=15000)
        return {"success": True, "title": page.title()}
    except Exception as e:
        return {"success": False, "error": str(e)}


def click_by_text(text: str) -> dict:
    """Accessibility-snapshot-based, not coordinate-based — same principle as
    app_control.py's click_control. Playwright's get_by_text/get_by_role read the
    page's real accessibility tree, not pixels."""
    page = get_page()
    try:
        page.get_by_text(text, exact=False).first.click(timeout=5000)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def read_page_text() -> str:
    page = get_page()
    return page.inner_text("body")[:8000]
```

Add as tools (`navigate_browser`, `click_on_page`, `read_page`), same dispatcher pattern as everything else. **Keep Gmail on the API route you already built** — this browser layer is for general sites without a dedicated API (search a product, check a webpage, fill an arbitrary form), not a replacement for the reliable email path.

**Confirmation rule:** pure navigation/reading needs no confirmation (matches your existing Tier 1/2 philosophy). Anything that submits a form, makes a purchase, or posts something publicly should go through the same confirm-before-act pattern as `send_email` and `delete_path`.

**Milestone check:** "search for the weather in Mumbai" navigates, reads the page, and answers — without ever confirming, since it's read-only. Then test a form-submission task and confirm it actually asks before submitting.

---

## Suggested build order

Phase 1 (file reading) → Phase 3 (app control, since Phase 2's Tier 0 depends on it) → Phase 2 (smart OCR) → Phase 4 (browser). Each has its own milestone check — don't start the next until the current one's check genuinely passes, same discipline that got the MVP working in the first place.
