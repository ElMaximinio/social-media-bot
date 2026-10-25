"""Ask Claude for the best clip moments in a stream transcript, with a hook and captions."""
import json

from .. import config

SYSTEM = """You pick viral TikTok clips from a streamer's or YouTuber's transcript.

A good clip:
- Stands alone: a viewer who has never seen the creator gets it without backstory.
- Opens on action or a strong line within the first 2 seconds. Start right before the payoff
  builds, not at a slow lead-in. End right after the payoff or the laugh, never mid-sentence.
- Has one clear emotion: shock, rage, a funny line, a fail, a win, a wholesome or awkward moment.
- Is 20 to 60 seconds long unless told otherwise.

For each clip, write:
- hook: on-screen title, 3 to 8 words, curiosity or stakes, no spoilers of the punchline, no emoji,
  no clickbait that the clip does not deliver (e.g. "He did NOT expect this answer").
- caption: TikTok caption under 150 characters with 3 to 5 hashtags, including the creator's name.
- why: one sentence on why it should do well.

Never invent what happens. Use only what the transcript shows. Avoid moments that are hateful,
sexual, about minors, or that mock a private person, even if they are popular."""

TOOL = {
    "name": "save_clips",
    "description": "Save the best clip candidates, best first.",
    "input_schema": {
        "type": "object",
        "properties": {
            "clips": {
                "type": "array",
                "minItems": 1,
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "properties": {
                        "start": {"type": "number", "description": "seconds from the start of the source"},
                        "end": {"type": "number"},
                        "hook": {"type": "string"},
                        "caption": {"type": "string"},
                        "why": {"type": "string"},
                    },
                    "required": ["start", "end", "hook", "caption", "why"],
                },
            }
        },
        "required": ["clips"],
    },
}


def transcript_lines(words: list[dict], every: float = 4.0) -> str:
    """Transcript with a [seconds] stamp about every few seconds, compact enough for long streams."""
    lines, cur, mark = [], [], None
    for w in words:
        if mark is None:
            mark = w["start"]
        cur.append(w["word"])
        if w["end"] - mark >= every:
            lines.append(f"[{mark:.1f}] {' '.join(cur)}")
            cur, mark = [], None
    if cur:
        lines.append(f"[{mark:.1f}] {' '.join(cur)}")
    return "\n".join(lines)


def pick_clips(words: list[dict], creator: str, rules: str = "", count: int = 3,
               min_len: float = 20, max_len: float = 60) -> list[dict]:
    import anthropic

    client = anthropic.Anthropic(api_key=config.require("ANTHROPIC_API_KEY"))
    prompt = (f"Creator: {creator}\nFind the {count} best clips, {min_len:.0f} to {max_len:.0f} seconds each.\n"
              + (f"Campaign rules to follow:\n{rules}\n" if rules else "")
              + f"\nTranscript (seconds in brackets):\n{transcript_lines(words)}")
    msg = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=3000,
        system=SYSTEM,
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "save_clips"},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in msg.content:
        if block.type == "tool_use":
            clips = block.input["clips"]
            return [snap(c, words) for c in clips]
    raise RuntimeError("Claude did not return clips")


def snap(clip: dict, words: list[dict], lead: float = 0.25, tail: float = 0.6) -> dict:
    """Move start and end onto word edges so the clip never cuts a word in half."""
    starts = [w["start"] for w in words if w["start"] >= clip["start"] - 1.5]
    ends = [w["end"] for w in words if w["end"] <= clip["end"] + 1.5]
    out = dict(clip)
    if starts:
        out["start"] = round(max(min(starts, key=lambda s: abs(s - clip["start"])) - lead, 0), 2)
    if ends:
        out["end"] = round(min(ends, key=lambda e: abs(e - clip["end"])) + tail, 2)
    return out


def save(clips: list[dict], path) -> None:
    path.write_text(json.dumps(clips, indent=2, ensure_ascii=False))
