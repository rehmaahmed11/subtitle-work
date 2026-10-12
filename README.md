# PERDE — Turkish audio → Urdu burned subtitles

A small atelier that follows one pipeline and does not invent timestamps:

1. **Audio → SRT** — extract 16 kHz mono from the video, transcribe Turkish, keep word-level start/end.
2. **Turkish → Urdu** — lock titles, honorifics (`Bey`, `Hanım`, `Paşa`…), Islamic formulae, and idioms to a glossary, then translate the rest. Cue times are copied, never rewritten.
3. **Hard-code** — shape Urdu, write an ASS file, burn it on the picture with a bundled Noto Naskh / Nastaliq font.
4. **Export** — `urdu_burned.mp4` plus both SRT files.

Two systems in one:

| | **Free** | **Paid** |
| --- | --- | --- |
| Speech | Local Whisper small, then base, then tiny | OpenAI Whisper-1 |
| Translate | **All** free engines in parallel — Google, MyMemory, LibreTranslate, plus the glossary/lexicon — then a majority vote | GPT-4o mini or GPT-4o with an idiom/title prompt |
| Key | none | `OPENAI_API_KEY` or the field in the UI |

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

Open the printed URL. Pick **Free** or **Paid**, drop a video (optionally a Turkish SRT), or press **Try the sample reel**.

## CLI

```bash
python cli.py film.mp4                          # free: all no-key models
python cli.py film.mp4 --tier paid --openai-key sk-...
python cli.py film.mp4 --srt film.tr.srt --font nastaliq
python cli.py film.mp4 --no-burn
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
