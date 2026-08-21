# src/tts.py
"""Piper TTS wrapper.

Synthesizes speech from text via the local ``piper.exe`` CLI and plays the
resulting ``data/out.wav`` through sounddevice. Exposes a single entry point,
``speak(text) -> bool``, that never raises — every failure path returns False
so the caller (main.py's REPL) can fall back to text-only mode gracefully.
"""

import os
import subprocess

import sounddevice as sd
import soundfile as sf

# Paths relative to project root
PIPER_EXE = os.path.join("piper", "piper.exe")
MODEL_PATH = os.path.join("models", "en_US-lessac-medium.onnx")
OUTPUT_WAV = os.path.join("data", "out.wav")


def speak(text: str) -> bool:
    """
    Synthesizes speech using Piper TTS and plays the resulting out.wav.

    Returns:
        True if audio played successfully, False otherwise.
    """
    if not text:
        return False

    # Ensure the data folder exists
    os.makedirs(os.path.dirname(OUTPUT_WAV) or ".", exist_ok=True)

    # Check if the piper executable and model exist
    if not os.path.exists(PIPER_EXE) or not os.path.exists(MODEL_PATH):
        print("Warning: Piper executable or model file missing!")
        return False

    # Run Piper to generate the audio file
    command = [PIPER_EXE, "--model", MODEL_PATH, "--output_file", OUTPUT_WAV]
    try:
        process = subprocess.run(
            command,
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=120,
        )
        if process.returncode != 0:
            stderr = process.stderr.decode("utf-8", errors="replace")
            print(f"Piper synthesis failed: {stderr}")
            return False
    except (subprocess.SubprocessError, OSError) as e:
        # Covers missing piper.exe, permission errors, and timeouts
        print(f"Piper could not run: {e}")
        return False

    # Play the generated WAV file (falls back gracefully if out.wav is locked)
    if not os.path.exists(OUTPUT_WAV):
        print("Warning: Piper did not produce an audio file.")
        return False

    try:
        data, fs = sf.read(OUTPUT_WAV)
        sd.play(data, fs)
        sd.wait()
        return True
    except Exception as e:
        print(f"Audio playback failed: {e}")
        return False

