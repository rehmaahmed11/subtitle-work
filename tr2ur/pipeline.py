"""End-to-end: video audio → Turkish SRT → Urdu SRT → hard-coded MP4."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .burn import burn_in
from .srt_io import load_srt, save_srt
from .transcribe import TranscribeError, extract_audio, transcribe_turkish
from .engines import resolve_openai_key
from .translate import Translator

ProgressCb = Callable[[str, int, str], None]


@dataclass
class PipelineResult:
    turkish_srt: Path
    urdu_srt: Path
    output_video: Path | None
    method: str
    stats: dict = field(default_factory=dict)
    cues: int = 0


def run_pipeline(
    video_path: str | Path | None,
    work_dir: str | Path,
    *,
    srt_path: str | Path | None = None,
    model_size: str = "small",
    font_key: str = "naskh",
    font_size: int = 52,
    burn: bool = True,
    prefer_online: bool = True,
    whisper_cache: str | None = None,
    progress: ProgressCb | None = None,
    tier: str = "free",
    openai_key: str | None = None,
    paid_model: str = "gpt-4o-mini",
) -> PipelineResult:
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)

    def report(step: str, pct: int, msg: str) -> None:
        if progress:
            progress(step, pct, msg)

    if not srt_path and not video_path:
        raise ValueError("Provide a video file, an SRT file, or both.")

    tier = "paid" if tier == "paid" else "free"
    key = resolve_openai_key(openai_key) if tier == "paid" else None
    if tier == "paid" and not key:
        raise ValueError("Paid mode needs an OpenAI API key (or OPENAI_API_KEY).")

    # --- 1. Turkish SRT ---
    if srt_path:
        report("srt", 12, "Reading Turkish SRT…")
        subs_tr = load_srt(srt_path)
        method = "provided-srt"
    else:
        report("audio", 8, "Extracting audio (16 kHz mono)…")
        wav = extract_audio(video_path, work / "audio_16k.wav")
        if tier == "paid":
            report("transcribe", 22, "Transcribing Turkish with OpenAI Whisper-1…")
        else:
            report(
                "transcribe",
                22,
                f"Free STT: local Whisper {model_size} (then base, tiny)…",
            )
        try:
            subs_tr = transcribe_turkish(
                wav,
                model_size=model_size,
                download_root=whisper_cache,
                tier=tier,
                openai_key=key,
            )
        except TranscribeError:
            raise
        method = "openai-whisper-1" if tier == "paid" else f"whisper-{model_size}"

    if not subs_tr:
        raise RuntimeError("No subtitle cues to translate.")

    tr_path = save_srt(subs_tr, work / "turkish.srt")
    if tier == "paid":
        report(
            "translate",
            48,
            f"Paid MT: {paid_model} on {len(subs_tr)} cues (titles · idioms)…",
        )
    else:
        report(
            "translate",
            48,
            f"Free MT: Google + MyMemory + Libre + lexicon on {len(subs_tr)} cues…",
        )

    translator = Translator(
        prefer_online=prefer_online,
        tier=tier,
        openai_key=key,
        paid_model=paid_model,
    )

    def tprog(i, n, how):
        pct = 48 + int(32 * i / max(n, 1))
        report("translate", pct, f"Translated {i}/{n} cues ({how})")

    subs_ur = translator.translate_subs(subs_tr, progress=tprog)
    ur_path = save_srt(subs_ur, work / "urdu.srt")

    out_video = None
    if burn:
        if not video_path:
            raise ValueError("Burn-in needs a video file.")
        report("burn", 84, "Hard-coding Urdu subtitles onto the video…")
        out_video = burn_in(
            video_path,
            subs_ur,
            work / "urdu_burned.mp4",
            font_key=font_key,
            font_size=font_size,
        )
        report("done", 100, "Export ready.")
    else:
        report("done", 100, "Urdu SRT ready (burn-in skipped).")

    return PipelineResult(
        turkish_srt=tr_path,
        urdu_srt=ur_path,
        output_video=out_video,
        method=f"{method}/{tier}",
        stats=translator.stats,
        cues=len(subs_ur),
    )
