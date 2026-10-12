"""Hard-code (burn in) Urdu subtitles onto a video with frame-accurate times."""

from __future__ import annotations

from pathlib import Path

from .ffmpeg_util import run_ffmpeg
from .rtl import prepare_ass_text, shape_urdu
from .srt_io import timedelta_to_ass

FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"

FONTS = {
    "naskh": ("Noto Naskh Arabic", "NotoNaskhArabic.ttf"),
    "nastaliq": ("Noto Nastaliq Urdu", "NotoNastaliqUrdu.ttf"),
}


def ass_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\n", r"\N")
    )


def _style_line(name: str, font: str, size: int, colour: str, align: int, bold: int, margin_v: int) -> str:
    # PrimaryColour is &HAABBGGRR
    return (
        f"Style: {name},{font},{size},{colour},&H000000FF,&HAA000000,&H64000000,"
        f"{bold},0,0,0,100,100,0,0,1,3,0,{align},80,80,{margin_v},1"
    )


def subs_to_ass(
    subs,
    *,
    font_key: str = "naskh",
    font_size: int = 52,
    play_res: tuple[int, int] = (1920, 1080),
    shape_rtl: bool = False,
) -> str:
    font_name, _ = FONTS.get(font_key, FONTS["naskh"])
    w, h = play_res
    title_size = max(font_size + 10, int(font_size * 1.2))
    header = f"""[Script Info]
Title: Turkish → Urdu burned subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: {w}
PlayResY: {h}
LayoutResX: {w}
LayoutResY: {h}
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{_style_line("Default", font_name, font_size, "&H00F4F1EA", 2, 0, 64)}
{_style_line("Title", font_name, title_size, "&H00A8D4E8", 5, 1, 80)}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for sub in subs:
        content = (sub.content or "").strip()
        if not content:
            continue
        style = "Title" if (getattr(sub, "proprietary", "") or "").upper() == "TITLE" else "Default"
        body = shape_urdu(content) if shape_rtl else prepare_ass_text(content)
        start = timedelta_to_ass(sub.start)
        end = timedelta_to_ass(sub.end)
        events.append(
            f"Dialogue: 0,{start},{end},{style},,0,0,0,,{ass_escape(body)}"
        )
    return header + "\n".join(events) + "\n"


def _escape_filter_path(path: Path) -> str:
    # FFmpeg filtergraph: escape \ : ' [ ]
    s = path.resolve().as_posix()
    s = s.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
    return s


def burn_in(
    video_path: str | Path,
    subs,
    output_path: str | Path,
    *,
    font_key: str = "naskh",
    font_size: int = 52,
    shape_rtl: bool = False,
    crf: int = 20,
    preset: str = "fast",
) -> Path:
    video_path = Path(video_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    work = output_path.parent
    ass_path = work / "urdu_burn.ass"
    ass_path.write_text(
        subs_to_ass(subs, font_key=font_key, font_size=font_size, shape_rtl=shape_rtl),
        encoding="utf-8",
    )

    fontsdir = FONTS_DIR
    if not fontsdir.exists():
        raise FileNotFoundError(f"Font directory missing: {fontsdir}")

    # ass filter uses libass; fontsdir lets it see the bundled Urdu fonts
    vf = f"ass={_escape_filter_path(ass_path)}:fontsdir={_escape_filter_path(fontsdir)}"
    run_ffmpeg(
        [
            "-i",
            str(video_path),
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-crf",
            str(crf),
            "-preset",
            preset,
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    if not output_path.exists() or output_path.stat().st_size < 1000:
        raise RuntimeError("Burn-in produced an empty video.")
    return output_path


def make_demo_video(path: str | Path, seconds: float = 12.0) -> Path:
    """A silent letterboxed slate so the pipeline can be tried without a film."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x140e0a:s=1280x720:d={seconds}:r=25",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=44100:duration={seconds}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ]
    )
    return path
