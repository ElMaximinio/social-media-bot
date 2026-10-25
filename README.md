# Wake Up In… — AI video pipeline

Makes first-person AI time-travel videos and posts them to TikTok, Instagram Reels and X.
Plan and research: https://claude.ai/artifact/Gf45GpN52DPjyCe8kDSco1

## How it works

1. **Script** (`bot/script.py`): Claude writes 8 beats (60–75 s) (narration + shot prompt), captions per platform, and a list of facts to check.
2. **Video** (`bot/video.py`): Gemini Omni Flash (`gemini-omni-1.1-flash`) renders one 9:16 clip per beat.
3. **Voice** (`bot/voice.py`): ElevenLabs reads each beat and returns word timings.
4. **Edit** (`bot/edit.py`): FFmpeg fits each clip to its narration, mixes the clip's sound low under the voice, burns in captions, and builds three cuts:
   - `tiktok.mp4`: the full episode (aim for 60 s+, needed for TikTok Creator Rewards)
   - `instagram.mp4`: up to 45 s
   - `x.mp4`: hook + peak beat, about 15 s
5. **Post** (`bot/post.py`): Upload-Post publishes or schedules all three, AI-generated label always on.

## Setup

```bash
pip install -r requirements.txt   # needs ffmpeg with libass
```

Environment variables (store as secrets, never commit):

| Variable | What |
| --- | --- |
| `ANTHROPIC_API_KEY` | Script writing |
| `GEMINI_API_KEY` | Video (Google AI Studio) |
| `ELEVENLABS_API_KEY` | Narration |
| `UPLOAD_POST_API_KEY` | Posting |
| `UPLOAD_POST_USER` | Upload-Post profile name (default `wakeupin`) |
| `BOT_VOICE_ID` | ElevenLabs voice for the narrator |

## Usage

```bash
python -m bot write "Salem, 1692, the witch trials"      # script to output/<slug>/episode.json, review it
python -m bot make output/salem-1692                      # clips + voice + edit
python -m bot make output/salem-1692 --dry-run            # offline test, placeholder clips and tones
python -m bot post output/salem-1692 --at 2026-10-31T18:00:00   # schedule (Europe/Paris)
```

Hand-written episodes live in `episodes/`; copy one to `output/<slug>/episode.json` to render it.
Generated clips are cached, so re-running `make` after editing captions or timing costs nothing.

Rule: review every episode (facts and video) before `post` for the first two weeks.

## Streamer clips (`bot/clips/`)

A second content type: vertical TikTok edits of streamer and YouTuber moments.

**Only clip creators who allow it.** Use a clipping campaign (Whop Content Rewards, or a creator's
own program in their Discord) or written permission. Campaigns usually give the source footage, the
rules (credit line, required hashtags, which platforms) and pay per 1,000 views. Reposting
other people's streams without permission risks takedowns and copyright strikes, and TikTok shows
unedited reposts to fewer people, so every clip gets real edits (layout, captions, hook, zooms).

How a clip is made:

1. **Find** (`clip find`): ElevenLabs Scribe transcribes the source with word timings, then Claude
   picks the best 20–60 s moments and writes a hook and caption for each (`candidates.json`).
   Without `ANTHROPIC_API_KEY` it saves `transcript.txt` and you fill in `clip.json` yourself.
2. **Make** (`clip make`):
   - cuts the moment and drops long quiet pauses (screams and laughs are kept),
   - finds faces (OpenCV YuNet) and picks a layout: **stack** (webcam on top, gameplay below),
     **track** (9:16 crop that follows the speaker) or **fit** (whole frame on a blurred copy),
   - punches in on the loudest moments, adds word-by-word captions (spoken word in yellow),
     a hook title and an optional credit line, and evens out the volume.
3. **Post** (`clip post`): Upload-Post, to a separate profile (`CLIPS_UPLOAD_POST_USER`, default
   `clips`) so clips don't mix with the Wake Up In… account. Campaign `required_tags` are added to the caption.

```bash
python -m bot clip find source.mp4 --creator "Name" --slug name-moment --rules rules.txt
# review output/clips/name-moment/clip.json (start, end, hook, caption, layout)
python -m bot clip make output/clips/name-moment       # writes tiktok.mp4 and render.json
python -m bot clip post output/clips/name-moment
```

`source` can be a URL (downloaded with yt-dlp) where the network allows it; cloud sessions
usually can't reach YouTube or Twitch, so pass a local file there.
