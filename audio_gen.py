import asyncio
import edge_tts

async def _generate(text: str, voice: str, output_path: str) -> None:
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


def generate_narration_audio(script_text: str, voice_model: str, output_path: str) -> str | None:
    if not script_text.strip():
        return None

    try:
        asyncio.run(_generate(script_text, voice_model, output_path))
        return output_path
    except Exception as e:
        print(f"[audio_gen] TTS generation failed, continuing text-only. Error: {e}")
        return None