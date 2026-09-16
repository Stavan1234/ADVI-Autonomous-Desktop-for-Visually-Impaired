# ADVI — Windows Setup & Run

## Requirements

- Windows 10/11
- Python 3.13.x (the project currently requires `>=3.13,<3.14`)
- Internet access for configured cloud LLM providers
- A working microphone is **not yet required by the current console build** because production speech-to-text input is not implemented yet.
- For desktop automation, the relevant Windows Python packages are installed by `requirements.txt` / `pip install -e .`.

## 1. Create the environment

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

## 2. Configure the LLM

Copy `.env.example` to `.env` and add at least one provider key:

```powershell
copy .env.example .env
```

Then edit `.env` and set `GROQ_API_KEY` and/or `GEMINI_API_KEY`.

## 3. Run

```powershell
advi
```

You can also run:

```powershell
python -m advi.app
```

## 4. Terminal trace

ADVI shows a compact per-turn trace such as:

```text
Input     search for ...
Route     action -> search (0.91)
Plan
  1. search — query='...'
Execution
  ✓ search, verified
ADVI      ...
```

This shows routing and execution summaries, not hidden model chain-of-thought. Detailed diagnostics remain in `logs/advi.log`.

Disable the compact trace with:

```powershell
$env:ADVI_TERMINAL_TRACE="0"
```

## 5. Desktop / GUI dependencies

The GUI packages are still part of the project and are required for local desktop/vision capabilities. They are imported lazily so ADVI can start and run non-GUI capabilities without crashing merely because a GUI backend is unavailable.

When a desktop/vision capability is actually used on Windows, its GUI dependencies are loaded normally.

## 6. Gmail

Gmail is optional. ADVI can run without Gmail credentials. To enable Gmail, provide the required OAuth files in `credentials/` as described by the Gmail integration code and complete the authorization flow.

## 7. Browser automation

Browser automation uses the project's Chrome/CDP integration. The application may launch/manage an ADVI-owned Chrome instance when the browser capability needs one. It does not automatically take ownership of arbitrary Chrome processes.

## 8. David fallback

David remains a separate fallback agent. ADVI only hands work to it through the fallback policy/gateway after the primary system fails in a class of failure that is safe for fallback.

David's desktop and vision imports remain available for local execution; they are lazy-loaded to avoid import-time GUI failures.

## 9. Logs and runtime data

The application creates runtime state under `runtime/` and detailed logs under `logs/` as needed.

Those directories are intentionally absent from this distributable so the package starts clean on a new machine.
