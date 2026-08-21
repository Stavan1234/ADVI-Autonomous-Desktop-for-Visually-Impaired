# Project Features Status

## Built (Current MVP)
- **File System Indexing**: Resolves paths and locates files (`fs_index.py`).
- **Application Indexing**: Resolves and launches applications (`app_index.py`).
- **Email Tools**: Send and manage emails with a confirmation prompt (`email_tool.py`).
- **File Tools**: Delete files with safety checks/confirmations (`file_tool.py`).
- **Core Dispatcher**: Tool dispatcher pattern with "verify, don't assume" discipline (`brain.py`).
- **TTS**: Text-to-speech module (`tts.py`).

## Yet to Build (Phase 2 Build Plan)
- **Phase 1: File Reading**: Ability to open and understand contents of `.txt`, `.pdf`, and `.docx` files.
- **Phase 3: Deep Application Control**: Ability to act inside an opened application (typing, clicking UI buttons via `pywinauto`). (Recommended to build before Phase 2).
- **Phase 2: Smart OCR**: 3-tiered screen reading.
  - Tier 0: Accessibility tree (pywinauto/UIA) - free, instant text.
  - Tier 1: Local OCR (Tesseract) on a screenshot - fast raw text.
  - Tier 2: Vision Model (qwen) - for layout, images, and complex screens.
- **Phase 4: Browser Control**: Reusable persistent browser session (Playwright) to navigate, click, and read web pages without a dedicated API.
