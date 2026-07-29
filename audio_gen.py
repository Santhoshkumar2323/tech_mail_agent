"""
audio_gen.py
Module 3 — Converts the narration script to speech using edge-tts.
Plain narration only — no background music, no chimes.

edge-tts is an unofficial API and can fail unexpectedly. This module
NEVER raises — it returns None on failure so the pipeline can fall back
to a text-only email instead of aborting the whole run.
"""

import asyncio
import edge_tts


async def _generate(text: str, voice: str, output_path: str) -> None:
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


def generate_narration_audio(script_text: str, voice_model: str, output_path: str) -> str | None:
    """
    Returns the output file path on success, or None on failure.
    Caller should check for None and send a text-only email in that case.
    """
    if not script_text.strip():
        return None

    try:
        asyncio.run(_generate(script_text, voice_model, output_path))
        return output_path
    except Exception as e:
        print(f"[audio_gen] TTS generation failed, continuing text-only. Error: {e}")
        return None