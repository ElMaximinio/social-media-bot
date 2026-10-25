"""CLI.

  python -m bot write "New York, 29 October 1929, Black Tuesday"   # script only, for review
  python -m bot make output/new-york-1929                          # clips + voice + edit
  python -m bot make output/new-york-1929 --dry-run                # offline test with placeholders
  python -m bot post output/new-york-1929 [--at 2026-10-29T18:00:00]

Streamer clips (only creators who allow clipping):
  python -m bot clip find source.mp4 --creator "Name" --slug name-moment   # best moments + hook
  python -m bot clip make output/clips/name-moment                         # render tiktok.mp4
  python -m bot clip post output/clips/name-moment [--at ...]
"""
import argparse
import json
from pathlib import Path

from . import config, edit, script


def cmd_write(args) -> None:
    ep = script.write_episode(args.topic)
    ep_dir = config.OUTPUT_DIR / ep["slug"]
    ep_dir.mkdir(parents=True, exist_ok=True)
    script.save(ep, ep_dir / "episode.json")
    print(f"Wrote {ep_dir / 'episode.json'}")
    print(f"\n{ep['title']}\n")
    for i, b in enumerate(ep["beats"]):
        print(f"[{i}] {b['narration']}")
    print("\nFacts to check:")
    for f in ep["facts_to_check"]:
        print(f"  - {f}")


def cmd_make(args) -> None:
    ep_dir = Path(args.episode_dir)
    ep = json.loads((ep_dir / "episode.json").read_text())
    if args.dry_run:
        from . import dryrun as gen_v
        make_clip, narrate = gen_v.fake_clip, gen_v.fake_narration
    else:
        from . import video, voice
        make_clip = lambda i, dest: video.generate_clip(ep["beats"][i]["shot_prompt"], dest)
        narrate = voice.narrate

    for i, beat in enumerate(ep["beats"]):
        clip = ep_dir / f"clip{i}.mp4"
        if not clip.exists():
            print(f"clip {i}: generating")
            make_clip(i, clip)
        mp3, words_path = ep_dir / f"beat{i}.mp3", ep_dir / f"beat{i}.words.json"
        if not mp3.exists():
            print(f"voice {i}: generating")
            words = narrate(beat["narration"], mp3)
            words_path.write_text(json.dumps(words))

    outputs = edit.assemble(ep_dir, len(ep["beats"]), ep.get("peak_beat", 3))
    for platform, path in outputs.items():
        print(f"{platform}: {path} ({edit.duration(path):.1f} s)")


def cmd_post(args) -> None:
    from . import post
    print(json.dumps(post.publish_episode(Path(args.episode_dir), args.at), indent=2))


def cmd_clip_find(args) -> None:
    from .clips import make as clips
    rules = Path(args.rules).read_text() if args.rules else ""
    clip_dir = clips.find(args.source, args.creator, args.slug, rules, args.count, args.min, args.max)
    print(f"Wrote {clip_dir / 'clip.json'} (top pick) and candidates.json:\n")
    for i, c in enumerate(json.loads((clip_dir / "candidates.json").read_text())):
        print(f"[{i}] {c['start']:.1f}-{c['end']:.1f} s  {c['hook']}\n    {c['why']}")


def cmd_clip_make(args) -> None:
    from .clips import make as clips
    res = clips.make(Path(args.clip_dir), dry_run=args.dry_run)
    print(json.dumps({k: str(v) for k, v in res.items()}, indent=2))


def cmd_clip_post(args) -> None:
    from .clips import make as clips
    print(json.dumps(clips.post(Path(args.clip_dir), args.at), indent=2))


def main() -> None:
    p = argparse.ArgumentParser(prog="bot")
    sub = p.add_subparsers(required=True)
    w = sub.add_parser("write"); w.add_argument("topic"); w.set_defaults(fn=cmd_write)
    m = sub.add_parser("make"); m.add_argument("episode_dir"); m.add_argument("--dry-run", action="store_true")
    m.set_defaults(fn=cmd_make)
    po = sub.add_parser("post"); po.add_argument("episode_dir"); po.add_argument("--at")
    po.set_defaults(fn=cmd_post)

    c = sub.add_parser("clip", help="streamer clip edits").add_subparsers(required=True)
    cf = c.add_parser("find"); cf.add_argument("source"); cf.add_argument("--creator", required=True)
    cf.add_argument("--slug", required=True); cf.add_argument("--rules", help="text file with campaign rules")
    cf.add_argument("--count", type=int, default=3)
    cf.add_argument("--min", type=float, default=20); cf.add_argument("--max", type=float, default=60)
    cf.set_defaults(fn=cmd_clip_find)
    cm = c.add_parser("make"); cm.add_argument("clip_dir"); cm.add_argument("--dry-run", action="store_true")
    cm.set_defaults(fn=cmd_clip_make)
    cp = c.add_parser("post"); cp.add_argument("clip_dir"); cp.add_argument("--at")
    cp.set_defaults(fn=cmd_clip_post)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
