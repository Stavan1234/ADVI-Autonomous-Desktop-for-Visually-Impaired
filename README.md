# ADVI

**Autonomous Desktop for Visually Impaired**

A clean rebuild of the ADVI desktop-agent project.

The old project is treated as source material and reference material, not as the new architecture.

## Current Foundation

The foundation currently provides:

- deterministic startup and shutdown
- one Python package / one import path
- explicit environment configuration
- structured logging
- clean separation between runtime, I/O, providers, memory, personality, brain, and tools
- optional local Piper TTS support
- testable startup lifecycle

## Project Structure

```text
src/advi/
├── brain/          # Reasoning and orchestration
├── core/           # Runtime, configuration, logging
├── io/             # Console and voice I/O
├── memory/         # Future memory systems
├── personality/    # Future identity and personality
├── providers/      # Future LLM/model providers
└── tools/          # Future executable tools
## Final Runtime Notes

The production path is now:

`input → reasoning → planning → policy → execution → observation → verification → bounded recovery/fallback → grounded response`

The terminal provides a compact human-readable pipeline trace while detailed diagnostics continue to be written to `logs/advi.log`.

The Windows GUI/vision dependencies used by ADVI and David are intentionally retained; they are lazy-loaded to avoid import-time GUI failures in environments where those capabilities are not being used.

Production speech-to-text microphone input is not currently implemented in the console build. Text input and configured TTS output are supported.
