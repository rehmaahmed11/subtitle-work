# PERDE — Turkish audio → Urdu burned subtitles

A small atelier that follows one pipeline and does not invent timestamps:

1. **Audio → SRT** — extract 16 kHz mono from the video, transcribe Turkish with Whisper (`faster-whisper`), keep word-level start/end.
2. **Turkish → Urdu** — lock titles, honorifics (`Bey`, `Hanım`, `Paşa`…), Islamic formulae, and idioms to a glossary, then translate the rest (Google when the network allows, otherwise an offline lexicon). Cue times are copied, never rewritten.
3. **Hard-code** — shape Urdu (reshaper + bidi), write an ASS file, burn it on the picture with libass and a bundled Noto Naskh / Nastaliq font.
4. **Export** — `urdu_burned.mp4` plus both SRT files.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

FFmpeg is pulled in via `imageio-ffmpeg` if it is not already on `PATH`.

The first Whisper run downloads a model (tiny / base / small / medium). If that is blocked, pass an existing Turkish `.srt` and the rest of the pipeline still runs.

## Web app

```bash
python app.py
```

Open the printed URL. Drop a video, optionally a Turkish SRT, or press **Try the 14-second demo**.

## CLI

```bash
python cli.py film.mp4
python cli.py film.mp4 --srt film.tr.srt --font nastaliq
python cli.py film.mp4 --no-burn          # SRT only
python cli.py --web
```

## What is treated specially

| Kind | Behaviour |
| --- | --- |
| Title cards (`BİRİNCİ BÖLÜM`, `Önceki bölümde`) | Title vocabulary, centred ASS style |
| Honorifics | Name kept, title mapped (`Ahmet Bey` → `Ahmet صاحب`) |
| Idioms | Non-literal Urdu (`İş işten geçti` → `اب دیر ہو چکی`) |
| Islamic phrases | Canonical form (`İnşallah` → `ان شاء اللہ`) |
| `[kapı çalar]` SFX | Translated inside the brackets |

Fonts live in `fonts/` (OFL). Naskh is the default for burned video; Nastaliq is optional.
