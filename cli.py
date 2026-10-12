#!/usr/bin/env python3
"""Turkish video/SRT → Urdu burned subtitles.

Examples:
  python cli.py film.mp4
  python cli.py film.mp4 --srt film.tr.srt
  python cli.py film.mp4 --model small --font nastaliq
  python cli.py --web
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Audio → Turkish SRT → Urdu (idioms/titles) → hard-coded video"
    )
    p.add_argument("video", nargs="?", help="Input video (mp4/mkv/mov/webm)")
    p.add_argument("--srt", help="Existing Turkish SRT (skips Whisper)")
    p.add_argument("--out", help="Output directory (default: ./outputs/<name>)")
    p.add_argument(
        "--model",
        default="small",
        choices=["tiny", "base", "small", "medium"],
        help="faster-whisper model for audio→SRT",
    )
    p.add_argument(
        "--font",
        default="naskh",
        choices=["naskh", "nastaliq"],
        help="Urdu burn-in font (naskh is cleaner on video)",
    )
    p.add_argument("--font-size", type=int, default=52)
    p.add_argument("--no-burn", action="store_true", help="Only write SRT files")
    p.add_argument(
        "--offline",
        action="store_true",
        help="Free tier: skip online MT, glossary/lexicon only",
    )
    p.add_argument(
        "--tier",
        default="free",
        choices=["free", "paid"],
        help="free = all no-key models; paid = OpenAI Whisper-1 + GPT",
    )
    p.add_argument("--openai-key", help="OpenAI API key (or OPENAI_API_KEY)")
    p.add_argument(
        "--paid-model",
        default="gpt-4o-mini",
        choices=["gpt-4o-mini", "gpt-4o"],
        help="Paid translation model",
    )
    p.add_argument("--web", action="store_true", help="Start the web app")
    p.add_argument("--port", type=int, default=5000)
    args = p.parse_args(argv)

    if args.web:
        from app import run_server

        run_server(port=args.port)
        return 0

    if not args.video and not args.srt:
        p.print_help()
        return 2

    from tr2ur.pipeline import run_pipeline

    video = Path(args.video) if args.video else None
    srt = Path(args.srt) if args.srt else None
    name = (video or srt).stem
    work = Path(args.out) if args.out else Path("outputs") / name
    work.mkdir(parents=True, exist_ok=True)

    def prog(step, pct, msg):
        print(f"[{pct:3d}%] {step:10s} {msg}", flush=True)

    result = run_pipeline(
        video,
        work,
        srt_path=srt,
        model_size=args.model,
        font_key=args.font,
        font_size=args.font_size,
        burn=not args.no_burn and video is not None,
        prefer_online=not args.offline,
        progress=prog,
        tier=args.tier,
        openai_key=args.openai_key,
        paid_model=args.paid_model,
    )
    print()
    print("Turkish SRT :", result.turkish_srt)
    print("Urdu SRT    :", result.urdu_srt)
    if result.output_video:
        print("Burned video:", result.output_video)
    print("Cues        :", result.cues)
    print("Stats       :", result.stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
