# Wake Up In… — AI video pipeline

Makes first-person AI time-travel videos and posts them to TikTok, Instagram Reels and X.
Plan and research: https://claude.ai/artifact/Gf45GpN52DPjyCe8kDSco1

## How it works

1. **Script** (`bot/script.py`): Claude writes 6 beats (narration + shot prompt), captions per platform, and a list of facts to check.
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
