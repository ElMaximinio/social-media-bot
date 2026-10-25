"""Write an episode script with Claude, returned as structured JSON."""
import json

from . import config

SYSTEM = """You write scripts for "Wake Up In…", a short-form channel of AI-made first-person
time-travel videos. Every episode drops the viewer into one specific place, date and moment.

Rules:
- Beat 1 is the hook: one sentence, spoken in the first 3 seconds, that starts "You wake up".
- 6 beats total. Each beat's narration is 14-22 words (about 6-9 seconds spoken).
- Escalate: place and date, then three rising beats, then the outcome, then a closing question
  that invites a comment (and promises the best answer picks a future episode).
- Second person, present tense, plain words, no exclamation marks.
- Only well-established historical facts. List every factual claim in facts_to_check.
- Never depict or name real living people. Historical figures may be mentioned, not shown up close.
- Each shot_prompt describes one 10-second first-person shot: setting, action, light, camera move.
"""

TOOL = {
    "name": "save_episode",
    "description": "Save the finished episode script.",
    "input_schema": {
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "kebab-case id, e.g. new-york-1929"},
            "title": {"type": "string", "description": "e.g. Wake Up In New York, 29 October 1929"},
            "beats": {
                "type": "array",
                "minItems": 6,
                "maxItems": 6,
                "items": {
                    "type": "object",
                    "properties": {
                        "narration": {"type": "string"},
                        "shot_prompt": {"type": "string"},
                    },
                    "required": ["narration", "shot_prompt"],
                },
            },
            "peak_beat": {"type": "integer", "description": "index (1-5) of the most striking beat, used for the X cut"},
            "captions": {
                "type": "object",
                "properties": {
                    "tiktok": {"type": "string", "description": "keyword-rich, under 300 chars, 3-5 hashtags"},
                    "instagram": {"type": "string", "description": "ends with a send-to-a-friend line, 3-5 hashtags"},
                    "x": {"type": "string", "description": "a question, under 200 chars, no hashtags"},
                },
                "required": ["tiktok", "instagram", "x"],
            },
            "facts_to_check": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["slug", "title", "beats", "peak_beat", "captions", "facts_to_check"],
    },
}


def write_episode(topic: str) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=config.require("ANTHROPIC_API_KEY"))
    msg = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=4000,
        system=SYSTEM,
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "save_episode"},
        messages=[{"role": "user", "content": f"Write the episode: {topic}"}],
    )
    for block in msg.content:
        if block.type == "tool_use":
            return block.input
    raise RuntimeError("Claude did not return an episode")


def save(episode: dict, path) -> None:
    path.write_text(json.dumps(episode, indent=2, ensure_ascii=False))
