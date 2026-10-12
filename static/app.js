const form = document.getElementById("form");
const zone = document.getElementById("zone");
const picked = document.getElementById("picked");
const video = document.getElementById("video");
const srt = document.getElementById("srt");
const rail = document.getElementById("rail");
const result = document.getElementById("result");
const bar = document.getElementById("bar");
const statusEl = document.getElementById("status");
const steps = [...document.querySelectorAll(".steps li")];
const go = document.getElementById("go");
const demoBtn = document.getElementById("demo");

function names() {
  const bits = [];
  if (video.files[0]) bits.push("Video: " + video.files[0].name);
  if (srt.files[0]) bits.push("SRT: " + srt.files[0].name);
  picked.textContent = bits.join(" · ") || "No files yet.";
}
video.addEventListener("change", names);
srt.addEventListener("change", names);

["dragenter", "dragover"].forEach((ev) => {
  zone.addEventListener(ev, (e) => {
    e.preventDefault();
    zone.classList.add("hot");
  });
});
["dragleave", "drop"].forEach((ev) => {
  zone.addEventListener(ev, (e) => {
    e.preventDefault();
    zone.classList.remove("hot");
  });
});
zone.addEventListener("drop", (e) => {
  const files = [...e.dataTransfer.files];
  const vid = files.find((f) => /video|\.(mp4|mkv|mov|webm|avi)$/i.test(f.type + f.name));
  const sub = files.find((f) => /\.srt$/i.test(f.name));
  if (vid) {
    const dt = new DataTransfer();
    dt.items.add(vid);
    video.files = dt.files;
  }
  if (sub) {
    const dt = new DataTransfer();
    dt.items.add(sub);
    srt.files = dt.files;
  }
  names();
});

let currentTier = "free";
let catalogue = { free: { stt: [], mt: [] }, paid: { stt: [], mt: [] } };

document.querySelectorAll(".tier").forEach((btn) => {
  btn.addEventListener("click", () => setTier(btn.dataset.tier));
});

function setTier(tier) {
  currentTier = tier === "paid" ? "paid" : "free";
  document.querySelectorAll(".tier").forEach((b) => {
    const on = b.dataset.tier === currentTier;
    b.classList.toggle("on", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
  document.getElementById("paid-box").hidden = currentTier !== "paid";
  renderEngines();
}

function renderEngines() {
  const pack = catalogue[currentTier] || { stt: [], mt: [] };
  const ul = document.getElementById("engine-list");
  ul.innerHTML = "";
  [...(pack.stt || []), ...(pack.mt || [])].forEach((e) => {
    const li = document.createElement("li");
    li.textContent = e.label;
    li.title = e.role || "";
    ul.appendChild(li);
  });
}

fetch("/api/tiers")
  .then((r) => r.json())
  .then((data) => {
    catalogue = data;
    renderEngines();
  })
  .catch(() => renderEngines());

form.addEventListener("submit", (e) => {
  e.preventDefault();
  start(false);
});
demoBtn.addEventListener("click", () => start(true));

async function start(demo) {
  if (currentTier === "paid" && !document.getElementById("openai_key").value.trim()) {
    rail.hidden = false;
    setProgress("error", 0, "Paid mode needs an OpenAI API key.");
    return;
  }
  const fd = new FormData();
  if (demo) fd.append("demo", "1");
  if (video.files[0]) fd.append("video", video.files[0]);
  if (srt.files[0]) fd.append("srt", srt.files[0]);
  fd.append("model", document.getElementById("model").value);
  fd.append("font", document.getElementById("font").value);
  fd.append("font_size", document.getElementById("font_size").value);
  fd.append("burn", document.getElementById("burn").checked ? "1" : "0");
  fd.append("tier", currentTier);
  fd.append("openai_key", document.getElementById("openai_key").value || "");
  fd.append("paid_model", document.getElementById("paid_model").value);

  go.disabled = true;
  demoBtn.disabled = true;
  result.hidden = true;
  rail.hidden = false;
  setProgress("queued", 2, "Sending…");

  const res = await fetch("/api/process", { method: "POST", body: fd });
  const data = await res.json();
  if (!res.ok) {
    setProgress("error", 0, data.error || "Failed to start");
    go.disabled = false;
    demoBtn.disabled = false;
    return;
  }
  poll(data.id);
}

function setProgress(step, pct, message) {
  bar.style.width = Math.max(0, Math.min(100, pct)) + "%";
  statusEl.textContent = message || step;
  const order = ["audio", "transcribe", "srt", "translate", "burn", "done"];
  const idx = order.indexOf(step);
  steps.forEach((li) => {
    const s = li.getAttribute("data-step");
    li.classList.remove("on", "done");
    const liIdx = ["audio", "transcribe", "translate", "burn"].indexOf(s);
    if (step === "srt" && s === "transcribe") li.classList.add("on");
    if (idx > liIdx && liIdx >= 0) li.classList.add("done");
    if ((step === s) || (step === "start" && s === "audio")) li.classList.add("on");
    if (step === "done") li.classList.add("done");
  });
}

async function poll(id) {
  const tick = async () => {
    const res = await fetch("/api/job/" + id);
    const j = await res.json();
    setProgress(j.step, j.percent, j.message);
    if (j.status === "done") {
      showResult(j.result);
      go.disabled = false;
      demoBtn.disabled = false;
      return;
    }
    if (j.status === "error") {
      statusEl.textContent = j.error || "Failed";
      go.disabled = false;
      demoBtn.disabled = false;
      return;
    }
    setTimeout(tick, 700);
  };
  tick();
}

function showResult(r) {
  result.hidden = false;
  const meta = document.getElementById("meta");
  meta.textContent = `${r.cues} cues · ${r.method} · ${JSON.stringify(r.stats)}`;
  const dl = document.getElementById("downloads");
  dl.innerHTML = "";
  const add = (href, label) => {
    if (!href) return;
    const a = document.createElement("a");
    a.className = "btn gold";
    a.href = href;
    a.textContent = label;
    a.setAttribute("download", "");
    dl.appendChild(a);
  };
  add(r.video, "Download burned MP4");
  add(r.urdu_srt, "Urdu SRT");
  add(r.turkish_srt, "Turkish SRT");

  const player = document.getElementById("player");
  if (r.video) {
    player.src = r.video;
    player.hidden = false;
  } else {
    player.removeAttribute("src");
    player.hidden = true;
  }
  const box = document.getElementById("cues");
  box.innerHTML = "";
  (r.preview || []).forEach((c) => {
    const d = document.createElement("div");
    d.className = "cue";
    d.innerHTML = `<div class="tr">${esc(c.start)} — ${esc(c.tr)}</div><div class="ur">${esc(c.ur)}</div>`;
    box.appendChild(d);
  });
}

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
