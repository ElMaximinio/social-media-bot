"""CLI.

  python -m bot write "New York, 29 October 1929, Black Tuesday"   # script only, for review
  python -m bot make output/new-york-1929                          # clips + voice + edit
  python -m bot make output/new-york-1929 --dry-run                # offline test with placeholders
  python -m bot post output/new-york-1929 [--at 2026-10-29T18:00:00]
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


def main() -> None:
    p = argparse.ArgumentParser(prog="bot")
    sub = p.add_subparsers(required=True)
    w = sub.add_parser("write"); w.add_argument("topic"); w.set_defaults(fn=cmd_write)
    m = sub.add_parser("make"); m.add_argument("episode_dir"); m.add_argument("--dry-run", action="store_true")
    m.set_defaults(fn=cmd_make)
    po = sub.add_parser("post"); po.add_argument("episode_dir"); po.add_argument("--at")
    po.set_defaults(fn=cmd_post)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
