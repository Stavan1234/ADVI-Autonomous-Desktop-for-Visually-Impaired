"""Shadow Brain — the orchestration layer for the assistant.

Owns the Groq client, tool schemas, conversation memory, Groq-free local
short-circuits (file search), path-safety rules, and the tool-execution loop.
main.py is now a thin REPL that feeds text in and speaks a CommandResult back.

Architecture:
  * A keyword-based intent registry (``open``/``launch`` -> app_tool,
    ``search file``/``find file``/``locate file`` -> file_tool, ``send email``/
    ``email`` -> email_tool) gives a fast, deterministic, Groq-free path for
    commands that don't need the model.
  * Anything the registry can't handle confidently falls through to the LLM
    tool-calling path, which handles structured extraction (e.g. email
    recipient/subject/body) and conversational replies.
  * app_tool is wired into both paths: the ``open_application`` LLM tool now
    delegates to ``app_tool.launch_app(name) -> tuple[bool, str]``, and the
    registry handler calls it directly.

What was fixed / made smart:
  * brain.py previously exposed only a bare ``chat()`` function, while the
    appended second half of main.py tried ``from brain import Brain,
    CommandResult`` — an ImportError waiting to happen. ``Brain`` and
    ``CommandResult`` are now real and live here.
  * main.py previously contained two concatenated, mutually-incompatible
    versions (a monolithic script *and* an OOP loop) with two ``if __name__``
    blocks. main.py is now a single thin REPL.
  * ``chat()`` previously sent ``tools=None`` + ``tool_choice="auto"`` on every
    request and retried rate limits with unbounded recursion. Tools are now
    optional, and rate limits use bounded exponential backoff (2s / 4s / 6s).
  * Conversation memory is owned by ``Brain`` and trimmed to a bounded window so
    long sessions don't overflow the model context window.
  * ``app_tool.py`` previously used the ``start <name>`` shell hack, which
    reported success unconditionally. It now resolves against the real
    installed-app index via ``app_index`` and reports truthfully.
"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from dotenv import load_dotenv
from groq import Groq

from tts import speak
from contacts import (
    resolve_contact,
    is_valid_email_format,
    domain_can_receive_mail,
    save_contact,
)
from email_tool import send_email, verify_sent
from file_tool import create_folder, delete_path
import file_tool
import fs_index
import app_index
import app_tool
import file_reader
import app_control

logger = logging.getLogger(__name__)

load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not found in .env file or environment variables")

client = Groq(api_key=GROQ_API_KEY)

# llama-3.3-70b-versatile was deprecated by Groq (June 17, 2026).
# gpt-oss-120b supports tool-calling on the generous free tier.
MODEL = "openai/gpt-oss-120b"

_RATE_LIMIT_CODES = (429,)
_RATE_LIMIT_RETRIES = 3


def chat(messages, tools=None, max_retries=_RATE_LIMIT_RETRIES):
    """One model call with bounded backoff on Groq rate-limit errors.

    ``tools`` is only sent when provided — sending ``tools=None`` alongside
    ``tool_choice="auto"`` can trip some SDK/API versions.
    """
    request = {"model": MODEL, "messages": messages}
    if tools:
        request["tools"] = tools
        request["tool_choice"] = "auto"

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(**request)
            return response.choices[0].message
        except Exception as e:
            code = getattr(e, "status_code", None)
            limited = (code in _RATE_LIMIT_CODES) or ("rate_limit" in str(e).lower())
            if not limited or attempt == max_retries - 1:
                raise
            time.sleep(2 * (attempt + 1))  # 2s, 4s, 6s


@dataclass
class CommandResult:
    """What the brain produces for a single user command."""
    message: str
    success: bool = True
    data: Optional[Any] = field(default=None)


# ── Path safety ────────────────────────────────────────────────────────────────
# Keep Shadow out of genuinely dangerous system directories rather than fencing
# it inside its own repo (which broke the whole "control the laptop" use case).

_WINDIR = os.environ.get("WINDIR", r"C:\Windows")
_PROGRAMFILES = os.environ.get("PROGRAMFILES", r"C:\Program Files")
_PROGRAMFILES_X86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
DANGEROUS_PREFIXES = [p for p in (_WINDIR, _PROGRAMFILES, _PROGRAMFILES_X86) if p]


# ── Local file-search queries — never touch Groq ──────────────────────────────

_FIND_FILES_PATTERN = re.compile(
    r"\b(find|show|search|list)\b.*?(?<!\.)\b(pdf|docx?|txt|xlsx?|png|jpe?g|pptx?)s?\b(?:.*?\b(?:in|on)\s+(\w+))?",
    re.IGNORECASE,
)
_MODIFIED_PATTERN = re.compile(r"\bmodified\s+(today|yesterday|this week)\b", re.IGNORECASE)


class Brain:
    """Stateful assistant brain: intent registry + LLM tools + conversation memory."""

    # Tool schemas exposed to the model. resolve_contact is deliberately NOT a
    # tool: contact resolution is a deterministic local fuzzy-match handled in
    # _execute_tool, which avoids the model-chains-two-tool-calls instability.
    TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "send_email",
                "description": "Send an email via Gmail. 'to' may be either a contact name "
                                "(e.g. 'Stark') or a full email address — Shadow resolves names "
                                "automatically, do not call any other tool to look it up first.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "Recipient name or email address"},
                        "subject": {"type": "string", "description": "Email subject line"},
                        "body": {"type": "string", "description": "Email body text"},
                    },
                    "required": ["to", "subject", "body"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_folder",
                "description": "Create a new folder/directory. Path may be a bare known-location "
                                "name (Desktop, Documents, Downloads, Pictures), a name inside one "
                                "of those (e.g. 'Desktop/Projects'), or a full absolute path.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Folder path or name to create"},
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_path",
                "description": "Delete a file or folder (use with caution)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path to delete"},
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_text_file",
                "description": "Write text content to a file (creates or overwrites)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path or name (e.g. 'Desktop/verse.txt')"},
                        "content": {"type": "string", "description": "Text content to write"},
                    },
                    "required": ["path", "content"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "open_application",
                "description": "Launch an installed application by its common name (e.g. 'whatsapp', "
                                "'telegram', 'notepad'). Shadow resolves this against what's actually "
                                "installed on the machine — do not guess a file path yourself.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "app_name": {"type": "string", "description": "Application name as the user said it"},
                    },
                    "required": ["app_name"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_file",
                "description": "Search the local filesystem index for a specific file by name.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "The name or partial name of the file to search for."},
                    },
                    "required": ["filename"],
                    "additionalProperties": False,
                },
            },
        },
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
    ]

    MAX_RETRIES = 3
    MAX_HISTORY = 30  # keep the system prompt + the most recent N messages

    def __init__(self):
        self._started = False
        self._registry: dict[str, Callable[[str], Optional[CommandResult]]] = {}
        self._register_default_tools()
        self.messages = [
            {
                "role": "system",
                "content": (
                    "You are Shadow, a highly capable AI assistant running directly on the user's system. "
                    "You have already indexed the user's filesystem (Desktop, Documents, Downloads, Pictures) and all installed apps. "
                    "You have tools to: search for files by name, read files (txt/pdf/docx), create/delete files and folders, "
                    "write text files, launch apps, type/click inside apps, and send emails. "
                    "When the user asks for one of these actions, call the appropriate tool directly using the function-calling mechanism. "
                    "For send_email, pass the recipient exactly as the user said it — Shadow resolves names automatically. "
                    "Do not claim you cannot scan or read the system; you have tools for it. Use them.\n\n"
                    "You are a desktop automation agent. NEVER generate file content, poems, or application text directly in the chat terminal. "
                    "You must strictly use your provided tools to write to files or type into applications. "
                    "If a UI or typing tool fails, report the failure to the user. Do not simulate or roleplay the output in the console."
                ),
            }
        ]

    # ── Intent registry ────────────────────────────────────────────────────────

    def register_handler(self, keyword: str, handler: Callable[[str], Optional[CommandResult]]) -> None:
        """Register a keyword -> handler mapping for the Groq-free fast path."""
        self._registry[keyword.lower().strip()] = handler

    def _register_default_tools(self) -> None:
        """Register the default intent keywords to their handlers."""
        self.register_handler("open", self._handle_open_app)
        self.register_handler("launch", self._handle_open_app)
        self.register_handler("search file", self._handle_file_search)
        self.register_handler("find file", self._handle_file_search)
        self.register_handler("locate file", self._handle_file_search)
        self.register_handler("send an email", self._handle_send_email)
        self.register_handler("send email", self._handle_send_email)
        self.register_handler("email", self._handle_send_email)

    # ── Intent handlers ────────────────────────────────────────────────────────

    def _handle_open_app(self, app_name: str) -> Optional[CommandResult]:
        """Fast-path app launch via app_tool (no Groq round-trip)."""
        if not app_name:
            return CommandResult("Which application should I open?", success=False)
        try:
            success, msg = app_tool.launch_app(app_name)
            if not success and "couldn't find" in msg.lower():
                return None  # Fall back to LLM for compound commands
            return CommandResult(msg, success=success)
        except AttributeError:
            logger.error("app_tool module does not expose 'launch_app(name)'.")
            return CommandResult("Application launcher tool is misconfigured.", success=False)
        except Exception:
            logger.exception("Failed to execute application launch.")
            return CommandResult(f"Failed to launch {app_name}.", success=False)

    def _handle_file_search(self, query: str) -> Optional[CommandResult]:
        """Fast-path name-based file search via file_tool (no Groq round-trip)."""
        if not query:
            return CommandResult("What file name should I look for?", success=False)
        try:
            # Invoking file_tool interface
            success, msg, matches = file_tool.search_file(query)
            return CommandResult(msg, success=success, data=matches)
        except AttributeError:
            logger.error("file_tool module does not expose 'search_file(name)'.")
            return CommandResult("File search tool is misconfigured.", success=False)
        except Exception:
            logger.exception("Failed to execute file search.")
            return CommandResult(f"An error occurred while searching for {query}.", success=False)

    def _handle_send_email(self, query: str) -> Optional[CommandResult]:
        """Fast-path for email intents such as 'send email to david saying I'll be late'
        or 'email david'. Parses the recipient (and an optional body after the word
        'saying'), then reuses the safe, confirmation-guarded send flow in
        _execute_tool. Returns None when nothing parseable is found so
        process_command falls through to the LLM for structured extraction."""
        query = (query or "").strip()
        if not query:
            return None  # not enough info -> LLM asks for details

        recipient = query
        subject = "Message from S.H.A.D.O.W."
        body = "Sent via S.H.A.D.O.W. AI Assistant."

        # "to <recipient> saying <body>" or "<recipient> saying <body>"
        saying = re.split(r"\bsaying\b", query, maxsplit=1, flags=re.IGNORECASE)
        if len(saying) == 2:
            recipient = re.sub(r"^to\s+", "", saying[0], flags=re.IGNORECASE).strip()
            body = saying[1].strip()
        elif recipient.lower().startswith("to "):
            recipient = recipient[3:].strip()

        if not recipient:
            return None  # nothing concrete to send to -> LLM handles it

        try:
            # Reuse the full guarded flow (contact resolution + confirmations).
            raw = self._execute_tool(
                "send_email",
                {"to": recipient, "subject": subject, "body": body},
            )
            result = json.loads(raw)
            success = bool(result.get("success"))
            if success:
                message = "Email sent."
            else:
                message = f"Email failed: {result.get('error', 'unknown error')}"
            return CommandResult(message, success=success)
        except Exception:
            logger.exception("Failed to run email fast-path.")
            return CommandResult(
                "An error occurred while attempting to send the email.", success=False
            )

    def _handle_unknown_intent(self, query: str) -> CommandResult:
        return CommandResult("I'm not sure how to handle that command yet.", success=False)

    # ── Startup ────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Build the filesystem + installed-app indexes once, at startup."""
        if self._started:
            return
        print("Starting filesystem index (Desktop/Documents/Downloads/Pictures)...")
        fs_index.start_watcher()
        print("Starting installed-app index...")
        app_index.start_index()
        self._started = True

    # ── Groq helpers ───────────────────────────────────────────────────────────

    def _get_reply(self):
        """Call the model, retrying transient failures."""
        for attempt in range(self.MAX_RETRIES):
            try:
                return chat(self.messages, tools=self.TOOLS)
            except Exception as e:
                if attempt == self.MAX_RETRIES - 1:
                    raise
                wait = 2 * (attempt + 1)
                print(f"[retrying after error: {e}] waiting {wait}s...")
                time.sleep(wait)

    @staticmethod
    def _reply_to_message_dict(reply) -> dict:
        """Serialize an SDK message object into the exact API dict shape so
        tool-call chains round-trip reliably (appending the raw object was a
        plausible cause of chains silently breaking)."""
        msg = {"role": "assistant", "content": reply.content}
        tool_calls = getattr(reply, "tool_calls", None) or []
        if tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in tool_calls
            ]
        return msg

    def _trim_history(self) -> None:
        """Bound conversation memory so long sessions don't overflow the context window."""
        if len(self.messages) > self.MAX_HISTORY:
            self.messages = [self.messages[0]] + self.messages[-(self.MAX_HISTORY - 1):]

    # ── Path helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _sanitise_path(raw_path: str) -> str:
        """Resolve a bare known-location name, a name inside one, or an absolute path.

        Bare names like 'Desktop' resolve to the real Desktop via fs_index instead
        of silently falling through to abspath()'s cwd default — that was the
        original 'can't create files outside the project folder' bug."""
        raw_path = (raw_path or "").strip().replace("\\", "/")

        known = fs_index.resolve_known_location(raw_path)
        if known:
            return known

        parts = raw_path.split("/", 1)
        if len(parts) == 2:
            known_root = fs_index.resolve_known_location(parts[0])
            if known_root:
                return os.path.join(known_root, parts[1])

        expanded = os.path.expanduser(raw_path)
        if os.path.isabs(expanded):
            return os.path.abspath(expanded)

        # Bare relative names default to Desktop, not the project's cwd.
        return os.path.join(fs_index.KNOWN_ROOTS["desktop"], expanded)

    @staticmethod
    def _is_path_dangerous(path: str) -> bool:
        abs_path = os.path.abspath(path)
        return any(abs_path.lower().startswith(p.lower()) for p in DANGEROUS_PREFIXES)

    def _confirm_if_dangerous(self, path: str, action_desc: str) -> bool:
        if self._is_path_dangerous(path):
            return self._user_confirms(
                f"'{path}' is a system directory — {action_desc}. Are you absolutely sure?"
            )
        return True

    def _user_confirms(self, prompt: str) -> bool:
        print(prompt)  # keep console context even when TTS is audio-only
        speak(prompt)
        response = input("(yes/no): ").strip().lower()
        return response in ("yes", "y", "yeah", "sure", "ok", "okay")

    def _get_and_validate_email_from_user(self) -> str:
        while True:
            email = input("Enter email address: ").strip()
            if not is_valid_email_format(email):
                speak("That doesn't look like a valid email. Please try again.")
                continue
            if not domain_can_receive_mail(email):
                if self._user_confirms(
                    f"'{email.split('@')[-1]}' doesn't appear able to receive email — use it anyway?"
                ):
                    return email
                continue
            return email

    # ── Local file queries (Groq-free) ─────────────────────────────────────────

    def _try_local_file_query(self, user_input: str) -> Optional[str]:
        """Return a spoken answer for a local file-search intent, or None."""
        match = _FIND_FILES_PATTERN.search(user_input)
        if match:
            ext, root_hint = match.group(2), match.group(3)
            results = fs_index.find_by_extension(ext, root_hint)
            location = f" in {root_hint}" if root_hint else ""
            if not results:
                return f"I didn't find any .{ext} files{location}."
            names = ", ".join(r["name"] for r in results[:10])
            more = f", and {len(results) - 10} more" if len(results) > 10 else ""
            return f"Found {len(results)} .{ext} file(s){location}: {names}{more}."

        match = _MODIFIED_PATTERN.search(user_input)
        if match:
            when = match.group(1).lower()
            cutoffs = {
                "today": datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
                "yesterday": datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1),
                "this week": datetime.now() - timedelta(days=7),
            }
            results = fs_index.find_modified_since(cutoffs[when])
            if not results:
                return f"Nothing appears to have been modified {when}."
            names = ", ".join(r["name"] for r in results[:10])
            return f"{len(results)} item(s) modified {when}: {names}."

        return None

    # ── Tool dispatcher ────────────────────────────────────────────────────────

    def _execute_tool(self, fn_name: str, fn_args: dict) -> str:
        if fn_name == "send_email":
            to_value = str(fn_args.get("to", "")).strip()
            subject = str(fn_args.get("subject", "")).strip()
            body = str(fn_args.get("body", "")).strip()

            if not to_value:
                speak("I need a recipient — who should this go to?")
                return json.dumps({"success": False, "error": "No recipient provided."})

            # Resolve name -> email entirely locally, no Groq round-trip needed.
            if not is_valid_email_format(to_value):
                candidates = resolve_contact(to_value)
                if len(candidates) == 1:
                    name, email = candidates[0]
                    speak(f"I found {name} at {email}.")
                    to_value = email
                elif len(candidates) > 1:
                    names = ", ".join(n for n, _ in candidates)
                    speak(f"I found a few matches: {names}. Which one did you mean?")
                    chosen = input("Contact name: ").strip().lower()
                    match = next((e for n, e in candidates if n == chosen), None)
                    if not match:
                        speak("I couldn't match that — please give me the email directly.")
                        match = self._get_and_validate_email_from_user()
                    to_value = match
                else:
                    speak(f"I don't have '{to_value}' in contacts. What's their email address?")
                    email = self._get_and_validate_email_from_user()
                    save_contact(to_value, email)
                    speak(f"Saved {to_value} for next time.")
                    to_value = email

            # Defense in depth: only a plain, valid-looking email string reaches send_email.
            if not is_valid_email_format(to_value):
                speak("Something went wrong resolving that recipient — what's the correct email address?")
                to_value = self._get_and_validate_email_from_user()

            if not self._user_confirms(f"The recipient is {to_value} — is that correct?"):
                speak("Please enter the correct email address.")
                to_value = self._get_and_validate_email_from_user()

            speak(f"Subject: {subject}")
            speak(f"Body: {body}")
            if not self._user_confirms("Should I send this email?"):
                return json.dumps({"success": False, "error": "User cancelled."})

            result = send_email(recipient=to_value, subject=subject, body=body)
            if result["success"]:
                confirmed = verify_sent(result["message_id"])
                if confirmed:
                    speak("Sent, and confirmed in your Sent folder.")
                else:
                    speak("It sent, but I couldn't confirm it in Sent — worth a quick manual check.")
                return json.dumps({"success": True, "message_id": result["message_id"], "verified_in_sent": confirmed})
            speak(f"That didn't go through: {result['error']}")
            return json.dumps(result)

        elif fn_name == "create_folder":
            path = self._sanitise_path(str(fn_args.get("path", "")))
            if not self._confirm_if_dangerous(path, "creating a folder there is unusual"):
                return json.dumps({"success": False, "error": "User declined system path."})
            result = create_folder(path)
            speak(f"Folder created at {path}." if result["success"] else f"Failed: {result['error']}")
            return json.dumps(result)

        elif fn_name == "delete_path":
            path = self._sanitise_path(str(fn_args.get("path", "")))
            if not self._confirm_if_dangerous(path, "deleting something there could break Windows"):
                return json.dumps({"success": False, "error": "User declined system path."})
            if not self._user_confirms(f"Are you sure you want to delete '{path}'?"):
                return json.dumps({"success": False, "error": "User cancelled."})
            result = delete_path(path)
            speak(f"Deleted {path}." if result["success"] else f"Failed: {result['error']}")
            return json.dumps(result)

        elif fn_name == "search_file":
            filename = str(fn_args.get("filename", ""))
            success, msg, matches = file_tool.search_file(filename)
            speak(msg)
            return json.dumps({"success": success, "message": msg, "matches": matches})

        elif fn_name == "write_text_file":
            path = self._sanitise_path(str(fn_args.get("path", "")))
            if path.lower().endswith(".pdf") or path.lower().endswith(".docx"):
                error_msg = "Cannot write raw text to .pdf files to prevent corruption."
                speak(error_msg)
                return json.dumps({"success": False, "error": error_msg})
            if not self._confirm_if_dangerous(path, "writing a file there is unusual"):
                return json.dumps({"success": False, "error": "User declined system path."})
            try:
                parent = os.path.dirname(path)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(str(fn_args.get("content", "")))
                speak(f"File written to {path}.")
                return json.dumps({"success": True, "path": path})
            except Exception as e:
                speak(f"Error: {e}")
                return json.dumps({"success": False, "error": str(e)})

        elif fn_name == "open_application":
            app_name = str(fn_args.get("app_name", ""))
            # Delegates to app_tool.launch_app, which resolves against the real
            # installed-app index and reports the outcome truthfully.
            success, msg = app_tool.launch_app(app_name)
            speak(msg)
            return json.dumps({"success": success, "message": msg})

        elif fn_name == "read_file":
            path = self._sanitise_path(str(fn_args.get("path", "")))
            try:
                content = file_reader.read_file_content(path)
                return json.dumps({"success": True, "content": content})
            except Exception as e:
                return json.dumps({"success": False, "error": str(e)})

        elif fn_name == "type_into_app":
            text = str(fn_args.get("text", ""))
            current_app = app_control.get_foreground_window_title()
            if not self._user_confirms(f"The foreground app is '{current_app}'. Should I type into it?"):
                return json.dumps({"success": False, "error": "User cancelled."})
            result = app_control.type_into_foreground(text)
            if result.get("success"):
                speak("Typed successfully.")
            else:
                speak(f"Failed to type: {result.get('error')}")
            return json.dumps(result)

        elif fn_name == "click_ui_button":
            button_name = str(fn_args.get("button_name", ""))
            current_app = app_control.get_foreground_window_title()
            if not self._user_confirms(f"The foreground app is '{current_app}'. Should I click '{button_name}' in it?"):
                return json.dumps({"success": False, "error": "User cancelled."})
            result = app_control.click_control(button_name)
            if result.get("success"):
                speak(f"Clicked {button_name}.")
            else:
                speak(f"Failed to click: {result.get('error')}")
            return json.dumps(result)

        return json.dumps({"success": False, "error": f"Unknown tool: {fn_name}"})

    # ── Main entry point ───────────────────────────────────────────────────────

    def process_command(self, user_input: str) -> CommandResult:
        """Handle one user command and return what should be spoken back.

        Order of resolution:
          1. Empty input handling.
          2. Intent-registry fast path (deterministic, Groq-free).
          3. Local file-search regex short-circuit (Groq-free).
          4. LLM tool-calling / conversational fallback.
        """
        user_input = user_input.strip()
        if not user_input:
            return CommandResult("I didn't catch that. Could you repeat?", success=False)

        # 2. Intent-registry fast path. Handlers return None when they can't
        #    handle the request confidently — then we fall through.
        cleaned = user_input.lower()
        for keyword, handler in self._registry.items():
            if cleaned.startswith(keyword):
                query_arg = user_input[len(keyword):].strip()
                try:
                    result = handler(query_arg)
                except Exception:
                    logger.exception(f"Tool execution failed for intent '{keyword}'")
                    return CommandResult(
                        "I encountered an error while trying to process that command.",
                        success=False,
                    )
                if result is not None:
                    return result
                break  # matched keyword but handler declined -> fall through

        # 3. Groq-free local short-circuit for file-search queries
        local_answer = self._try_local_file_query(user_input)
        if local_answer:
            return CommandResult(local_answer)

        # 4. LLM path
        self.messages.append({"role": "user", "content": user_input})

        try:
            reply = self._get_reply()
        except Exception as e:
            self.messages.pop()
            return CommandResult(f"I'm having trouble reaching the AI service: {e}", success=False)

        # Execute any chained tool calls the model requested
        while getattr(reply, "tool_calls", None):
            self.messages.append(self._reply_to_message_dict(reply))
            for tool_call in reply.tool_calls:
                try:
                    fn_args = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError:
                    fn_args = {}
                try:
                    result = self._execute_tool(tool_call.function.name, fn_args)
                except Exception as e:
                    # Whatever goes wrong, Shadow stays alive and reports it.
                    speak(f"Something went wrong running {tool_call.function.name}: {e}")
                    result = json.dumps({"success": False, "error": str(e)})
                self.messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})
            try:
                reply = self._get_reply()
            except Exception as e:
                return CommandResult(f"I'm having trouble reaching the AI service: {e}", success=False)

        if reply.content:
            self.messages.append({"role": "assistant", "content": reply.content})
            self._trim_history()
            return CommandResult(reply.content)
        return CommandResult("")


def groq_speak(status_message: str) -> None:
    """
    Use Groq to generate a conversational, natural verbal response from an execution status,
    then speak it to the user.
    """
    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are S.H.A.D.O.W., a helpful desktop AI assistant. "
                    "Speak the following status to the user in a natural, conversational, "
                    "friendly and concise tone. DO NOT output any reasoning, JSON, or formatting. "
                    "Speak directly as the assistant."
                )
            },
            {"role": "user", "content": status_message}
        ]
        reply = chat(messages)
        content = reply.content.strip()
        try:
            print(f"Shadow: {content}")
        except UnicodeEncodeError:
            try:
                import sys
                print(f"Shadow: {content.encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8')}")
            except Exception:
                print("Shadow: [Conversational response generated, speaking now]")
        speak(content)
    except Exception as e:
        logger.error(f"Failed to generate Groq voice response: {e}")
        try:
            print(f"Shadow: {status_message}")
        except UnicodeEncodeError:
            try:
                import sys
                print(f"Shadow: {status_message.encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8')}")
            except Exception:
                print("Shadow: [Status response generated, speaking now]")
        speak(status_message)


def run_shadow(user_input: str) -> None:
    """
    Run the shadow execution loop using Intent-Planner-Executor architecture.
    """
    # Local imports to prevent circular dependency or path issues
    try:
        from src.intent_parser import extract_intent
        from src.planner import generate_plan
        from src.contacts import get_email_by_name
        from src.email_tool import send_email
    except ImportError:
        from intent_parser import extract_intent
        from planner import generate_plan
        from contacts import get_email_by_name
        from email_tool import send_email
    import json

    current_input = user_input
    
    while True:
        # 1. Intent extraction
        intent_data = extract_intent(current_input)
        if not intent_data:
            groq_speak("I was unable to extract the intent from your request.")
            return

        # Print exact Gemini Intent JSON
        print(f"\n[Gemini Intent JSON]\n{json.dumps(intent_data, indent=2)}\n")

        # 2. Check for missing information
        missing_info = intent_data.get("missing_information", [])
        if missing_info:
            print(f"Missing information: {', '.join(missing_info)}")
            groq_speak(f"I need more information to complete your request. Please specify the missing details: {', '.join(missing_info)}.")
            return

        # 3. Generate action plan
        actions = generate_plan(intent_data)
        # Print exact Gemini Action Plan JSON
        print(f"\n[Gemini Action Plan JSON]\n{json.dumps(actions, indent=2)}\n")

        if not actions:
            # If no actions returned, break out of loop
            return

        feedback_given = False

        # 4. Iterate and execute actions
        for action_obj in actions:
            action = action_obj.get("action")
            params = action_obj.get("parameters", {})

            if action == "send_email_api":
                recipient = params.get("recipient", "")
                subject = params.get("subject", "")
                body = params.get("body", "")

                # Check if the recipient needs to be resolved
                if "@" not in recipient:
                    resolved = get_email_by_name(recipient)
                    if resolved:
                        to = resolved
                    else:
                        err_msg = f"Could not resolve recipient name '{recipient}' to an email address."
                        print(err_msg)
                        groq_speak(err_msg)
                        continue
                else:
                    to = recipient

                # Check if confirmation is required (default to True unless explicitly False)
                confirmation_required = intent_data.get("confirmation_required", True)
                
                if confirmation_required:
                    # Render drafted message cleanly to terminal
                    print(f"\n======================= DRAFT EMAIL =======================")
                    print(f"To:      {to}")
                    print(f"Subject: {subject}")
                    print(f"Body:    \n{body}")
                    print(f"===========================================================")
                    
                    user_choice = input("Press 'Y' to send, 'N' to cancel, or type your revisions/new instructions: ").strip()
                    
                    if user_choice.lower() in ("y", "yes"):
                        # Proceed with sending
                        pass
                    elif user_choice.lower() in ("n", "no"):
                        cancel_msg = "Email send cancelled by user"
                        print(cancel_msg)
                        groq_speak(cancel_msg)
                        return # Abort execution
                    else:
                        # Dynamic Feedback
                        print("\nDraft paused. Feeding feedback back to planner...")
                        current_input = f"Draft paused. User feedback: {user_choice}\n\nOriginal Draft:\nTo: {to}\nSubject: {subject}\nBody: {body}"
                        feedback_given = True
                        break # Break action loop to re-plan with new current_input

                print(f"Executing send_email to={to}, subject={subject}")
                result = send_email(to, subject, body)
                if result.get("success"):
                    groq_speak(f"Successfully sent the email to {to} with subject '{subject}'.")
                else:
                    groq_speak(f"Failed to send the email to {to}. Error details: {result.get('error')}.")
                    
            elif action == "open_application":
                app_name = params.get("app_name", "")
                try:
                    from src.app_tool import launch_app
                except ImportError:
                    from app_tool import launch_app
                success, msg = launch_app(app_name)
                groq_speak(msg)
                
            elif action == "search_web":
                print(f"Executing search_web query={params.get('query')}")
                # Simple web search fallback
                query = params.get("query", "")
                import urllib.parse
                import webbrowser
                webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(query)}")
                groq_speak(f"Searching Google for '{query}'.")

        # If we broke the actions loop due to user feedback, continue the while loop
        if feedback_given:
            continue
        else:
            # Otherwise we successfully completed the plan, so we can exit
            break
