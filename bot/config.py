import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = Path(os.environ.get("BOT_OUTPUT_DIR", ROOT / "output"))

ANTHROPIC_MODEL = os.environ.get("BOT_SCRIPT_MODEL", "claude-sonnet-5-5")
OMNI_MODEL = os.environ.get("BOT_VIDEO_MODEL", "gemini-omni-1.1-flash")
VIDEO_RESOLUTION = os.environ.get("BOT_VIDEO_RESOLUTION", "720p")

# Default narrator: set BOT_VOICE_ID to the ElevenLabs voice you pick for the brand.
ELEVENLABS_VOICE_ID = os.environ.get("BOT_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
ELEVENLABS_MODEL = os.environ.get("BOT_VOICE_MODEL", "eleven_multilingual_v2")

# Upload-Post profile name (the "user" you create in the Upload-Post dashboard).
UPLOAD_POST_USER = os.environ.get("UPLOAD_POST_USER", "wakeupin")
# Separate Upload-Post profile for streamer clips, so the two niches stay on different accounts.
CLIPS_UPLOAD_POST_USER = os.environ.get("CLIPS_UPLOAD_POST_USER", "clips")

# Visual style appended to every shot so clips look like one film.
STYLE = (
    "First-person POV, handheld, photorealistic period-accurate detail, "
    "35mm film grain, natural light, vertical 9:16 framing, no text on screen, "
    "no modern objects, no real identifiable people"
)


def require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing environment variable {name}. Add it to the cloud environment secrets.")
    return value
