#!/usr/bin/env python3
"""PERDE — Turkish → Urdu burned-subtitle atelier (Flask)."""

from __future__ import annotations

import shutil
import threading
import time
import uuid
from pathlib import Path

from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    send_file,
    send_from_directory,
    url_for,
)

from tr2ur.burn import make_demo_video
from tr2ur.engines import catalogue
from tr2ur.pipeline import run_pipeline
from tr2ur.srt_io import load_srt

ROOT = Path(__file__).resolve().parent
JOBS = ROOT / "jobs"
JOBS.mkdir(exist_ok=True)
EXAMPLE_SRT = ROOT / "examples" / "sample_tr.srt"

app = Flask(
    __name__,
    template_folder=str(ROOT / "templates"),
    static_folder=str(ROOT / "static"),
)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2 GB

_jobs: dict[str, dict] = {}
_lock = threading.Lock()


@app.after_request
def _headers(resp):
    resp.headers.pop("X-Frame-Options", None)
    resp.headers["Content-Security-Policy"] = (
        "frame-ancestors *; default-src 'self' 'unsafe-inline' blob: data:"
    )
    return resp


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/fonts/<path:name>")
def fonts(name: str):
    return send_from_directory(ROOT / "fonts", name)


@app.get("/api/tiers")
def api_tiers():
    return jsonify(catalogue())


def _new_job() -> dict:
    jid = uuid.uuid4().hex[:12]
    work = JOBS / jid
    work.mkdir(parents=True, exist_ok=True)
    job = {
        "id": jid,
        "work": str(work),
        "status": "queued",
        "step": "queued",
        "percent": 0,
        "message": "Waiting…",
        "error": None,
        "result": None,
        "created": time.time(),
    }
    with _lock:
        _jobs[jid] = job
    return job


def _update(job: dict, **kw) -> None:
    with _lock:
        job.update(kw)


def _run(job: dict, video: Path | None, srt: Path | None, opts: dict) -> None:
    def prog(step, pct, msg):
        _update(job, status="running", step=step, percent=pct, message=msg)

    try:
        _update(job, status="running", step="start", percent=4, message="Starting pipeline…")
        result = run_pipeline(
            video,
            job["work"],
            srt_path=srt,
            model_size=opts.get("model") or "small",
            font_key=opts.get("font") or "naskh",
            font_size=int(opts.get("font_size") or 52),
            burn=bool(opts.get("burn", True)) and video is not None,
            prefer_online=True,
            whisper_cache=str(ROOT / "jobs" / ".whisper"),
            progress=prog,
            tier=opts.get("tier") or "free",
            openai_key=opts.get("openai_key"),
            paid_model=opts.get("paid_model") or "gpt-4o-mini",
        )
        preview = []
        try:
            tr = load_srt(result.turkish_srt)
            ur = load_srt(result.urdu_srt)
            for a, b in zip(tr[:12], ur[:12]):
                preview.append({"tr": a.content, "ur": b.content, "start": str(a.start)})
        except Exception:
            preview = []
        payload = {
            "turkish_srt": f"/download/{job['id']}/turkish.srt",
            "urdu_srt": f"/download/{job['id']}/urdu.srt",
            "video": (
                f"/download/{job['id']}/urdu_burned.mp4" if result.output_video else None
            ),
            "cues": result.cues,
            "method": result.method,
            "stats": result.stats,
            "preview": preview,
        }
        _update(
            job,
            status="done",
            step="done",
            percent=100,
            message="Export ready.",
            result=payload,
        )
    except Exception as exc:
        _update(
            job,
            status="error",
            error=str(exc),
            message=str(exc),
            percent=job.get("percent") or 0,
        )


@app.post("/api/process")
def api_process():
    video_file = request.files.get("video")
    srt_file = request.files.get("srt")
    demo = request.form.get("demo") == "1"

    opts = {
        "model": request.form.get("model", "small"),
        "font": request.form.get("font", "naskh"),
        "font_size": request.form.get("font_size", "52"),
        "burn": request.form.get("burn", "1") != "0",
        "tier": request.form.get("tier", "free"),
        "openai_key": request.form.get("openai_key", "").strip(),
        "paid_model": request.form.get("paid_model", "gpt-4o-mini"),
    }

    job = _new_job()
    work = Path(job["work"])
    video_path = None
    srt_path = None

    if demo:
        video_path = make_demo_video(work / "source.mp4", seconds=34)
        src = EXAMPLE_SRT if EXAMPLE_SRT.exists() else None
        if src:
            srt_path = work / "input.srt"
            shutil.copy(src, srt_path)
    else:
        if video_file and video_file.filename:
            video_path = work / ("source" + _ext(video_file.filename, ".mp4"))
            video_file.save(video_path)
        if srt_file and srt_file.filename:
            srt_path = work / "input.srt"
            srt_file.save(srt_path)

    if not video_path and not srt_path:
        _update(job, status="error", error="Upload a video, an SRT, or run the demo.")
        return jsonify({"id": job["id"], "error": job["error"]}), 400

    t = threading.Thread(
        target=_run, args=(job, video_path, srt_path, opts), daemon=True
    )
    t.start()
    return jsonify({"id": job["id"]})


@app.get("/api/job/<jid>")
def api_job(jid: str):
    with _lock:
        job = _jobs.get(jid)
        if not job:
            return jsonify({"error": "unknown job"}), 404
        return jsonify(
            {
                "id": job["id"],
                "status": job["status"],
                "step": job["step"],
                "percent": job["percent"],
                "message": job["message"],
                "error": job["error"],
                "result": job["result"],
            }
        )


@app.get("/download/<jid>/<name>")
def download(jid: str, name: str):
    allowed = {
        "turkish.srt": "turkish.srt",
        "urdu.srt": "urdu.srt",
        "urdu_burned.mp4": "urdu_burned.mp4",
    }
    if name not in allowed:
        return "Not found", 404
    path = JOBS / jid / allowed[name]
    if not path.exists():
        return "Not found", 404
    as_attach = name.endswith(".srt") or name.endswith(".mp4")
    return send_file(path, as_attachment=as_attach, download_name=name)


def _ext(filename: str, default: str) -> str:
    suf = Path(filename).suffix.lower()
    if suf in {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"}:
        return suf
    return default


def run_server(host: str = "0.0.0.0", port: int = 5000) -> None:
    print(f"PERDE running on http://{host}:{port}")
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    run_server()
