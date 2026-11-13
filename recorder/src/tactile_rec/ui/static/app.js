// Tactile Recorder UI. No framework and no build step: this file is served as it is.
// The page only shows what the server reports and sends commands; all logic is on the server.
"use strict";

const $ = (id) => document.getElementById(id);
const FINGERS = [["thumb", "엄지"], ["index", "검지"], ["middle", "중지"], ["ring", "약지"]];
const SEGMENTS = [["tip", "끝"], ["pad", "마디"]];
const STATE_LABEL = { idle: "대기", recording: "녹화 중", review: "검토" };
const STATUS_LABEL = { ok: "정상", slow: "느림", stale: "끊김", error: "오류", off: "없음" };
const HAND_MODES = ["live", "hold", "release"];
const HAND_JOINT_LABELS = ["벌림", "MCP", "PIP", "DIP"];
const THUMB_JOINT_LABELS = ["벌림", "CMC", "MCP", "IP"];
const HAND_ORDER = [["thumb", 12], ["index", 0], ["middle", 4], ["ring", 8]]; // joint offset

let state = null;        // last "state" message
let info = null;         // /api/describe
let page = "record";
const hzHistory = {};    // stream -> recent Hz values, for the sparklines
const canvases = {};     // place -> {canvas, xy, fz element, box}

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const child of [].concat(children)) if (child) node.append(child);
  return node;
}

// ---- server ---------------------------------------------------------------------------------

async function api(method, path, body) {
  const response = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail || {};
    const problems = detail.problems || [typeof detail === "string" ? detail : response.statusText];
    const error = new Error(problems.join("\n"));
    error.problems = problems;
    throw error;
  }
  return data;
}

let toastTimer = 0;
function toast(message, bad = false) {
  const box = $("toast");
  box.textContent = message;
  box.className = bad ? "toast bad" : "toast";
  box.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { box.hidden = true; }, bad ? 6000 : 2500);
}

async function command(path, body, okMessage) {
  try {
    const result = await api("POST", path, body || {});
    if (okMessage) toast(okMessage);
    return result;
  } catch (error) {
    toast(error.message, true);
    return null;
  }
}

function connect() {
  const socket = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  socket.onopen = () => { $("conn-dot").className = "dot ok"; $("conn-text").textContent = "연결됨"; };
  socket.onclose = () => {
    $("conn-dot").className = "dot bad"; $("conn-text").textContent = "연결 끊김";
    setTimeout(connect, 1000);
  };
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "state") onState(message);
    else if (message.type === "live") onLive(message);
    else if (message.type === "notice") onNotice(message);
  };
}

async function loadInfo() {
  try {
    info = await api("GET", "/api/describe");
  } catch (error) {
    return;
  }
  buildCameras();
  buildFingers();
  renderSettings();
}

// ---- sound ----------------------------------------------------------------------------------
// The operator watches the robot, not the screen, so state changes are also audible.

let audio = null;
function beep(tones) {
  try {
    audio = audio || new (window.AudioContext || window.webkitAudioContext)();
    let at = audio.currentTime;
    for (const [hz, seconds] of tones) {
      const osc = audio.createOscillator(), gain = audio.createGain();
      osc.frequency.value = hz;
      gain.gain.setValueAtTime(0.12, at);
      gain.gain.exponentialRampToValueAtTime(0.001, at + seconds);
      osc.connect(gain).connect(audio.destination);
      osc.start(at); osc.stop(at + seconds);
      at += seconds + 0.04;
    }
  } catch (error) { /* no audio device: the screen still shows everything */ }
}

function onNotice(message) {
  if (message.kind === "start") beep([[880, 0.12]]);
  else if (message.kind === "stop") beep([[440, 0.18]]);
  else if (message.kind === "saved") beep([[660, 0.08], [990, 0.12]]);
  else if (message.kind === "discarded") beep([[330, 0.2]]);
  else if (message.kind === "dropout") {
    beep([[220, 0.15], [220, 0.15], [220, 0.15]]);
    toast(`${message.stream} 끊김`, true);
  } else if (message.kind === "recovered") toast(`${message.stream} 복구`);
  if (["saved", "discarded"].includes(message.kind) && page === "episodes") loadEpisodes();
}

// ---- record page ----------------------------------------------------------------------------

function buildCameras() {
  const box = $("cams");
  box.replaceChildren();
  for (const camera of info.cameras) {
    box.append(el("div", { class: "cam" }, [
      el("div", { class: "cam-frame" }, el("img", { src: `/api/stream/${camera.name}`, alt: `${camera.name} 미리보기` })),
      el("div", { class: "cam-cap" }, [
        el("span", { text: camera.name + (camera.rotation_deg ? ` · ${camera.rotation_deg}° 회전` : "") }),
        el("span", { class: "muted", id: `cam-hz-${camera.name}` }),
      ]),
    ]));
  }
  if (!info.cameras.length) box.append(el("p", { class: "muted", text: "설정에 카메라가 없습니다." }));
}

function buildFingers() {
  const box = $("fingers");
  box.replaceChildren();
  for (const key of Object.keys(canvases)) delete canvases[key];
  for (const [finger, fingerLabel] of FINGERS) {
    const column = el("div", { class: "finger" }, el("h3", { text: fingerLabel }));
    for (const [segment, segmentLabel] of SEGMENTS) {
      const place = `${finger}_${segment}`;
      const sensor = info.tactile[place];
      const canvas = el("canvas", { width: 220, height: 184 });
      const fz = el("div", { class: "fz", text: sensor ? "0.0" : "-" });
      const pad = el("div", { class: sensor ? "pad" : "pad off" }, [
        canvas,
        el("div", { class: "seg", text: sensor ? `${segmentLabel} · ${sensor.points}점` : `${segmentLabel} · 없음` }),
        fz,
      ]);
      column.append(pad);
      if (sensor) canvases[place] = { canvas, fz, xy: normalise(sensor.xy), pad };
    }
    box.append(column);
  }
  buildHand();
}

function normalise(xy) {
  // Fit the taxel coordinates (mm) into the canvas, keeping the aspect ratio. y grows toward
  // the fingertip, so it is flipped to point up.
  const xs = xy.map((p) => p[0]), ys = xy.map((p) => p[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const span = Math.max(maxX - minX, maxY - minY) || 1;
  return xy.map(([x, y]) => [
    0.5 + (x - (minX + maxX) / 2) / span * 0.82,
    0.5 - (y - (minY + maxY) / 2) / span * 0.82,
  ]);
}

function drawTactile(place, values) {
  const item = canvases[place];
  if (!item) return;
  const context = item.canvas.getContext("2d");
  const { width, height } = item.canvas;
  const full = Number($("tactile-scale").value);
  const radius = Math.max(4, Math.min(11, 150 / Math.sqrt(item.xy.length) / 1.6));
  context.clearRect(0, 0, width, height);
  item.xy.forEach(([x, y], index) => {
    const level = Math.min(1, (values.fz[index] || 0) / full);
    const shade = Math.round(222 - level * 205);       // light grey -> near black
    context.beginPath();
    context.arc(x * width, y * height, radius * (0.75 + 0.5 * level), 0, Math.PI * 2);
    context.fillStyle = level >= 1 ? "#c62828" : `rgb(${shade},${shade},${shade + 2})`;
    context.fill();
  });
  item.fz.textContent = values.r[2].toFixed(1);
}

function buildHand() {
  const box = $("hand");
  box.replaceChildren();
  for (const [finger, offset] of HAND_ORDER) {
    const labels = finger === "thumb" ? THUMB_JOINT_LABELS : HAND_JOINT_LABELS;
    const column = el("div", { class: "hand-finger" }, el("h3", { text: FINGERS.find((f) => f[0] === finger)[1] }));
    labels.forEach((label, k) => {
      column.append(el("div", { class: "joint", "data-joint": offset + k }, [
        el("span", { text: label }),
        el("span", { class: "track" }, [el("i", { class: "cmd" }), el("i", { class: "pos" })]),
        el("span", { class: "val", text: "-" }),
      ]));
    });
    box.append(column);
  }
}

function onLive(message) {
  if (page !== "record" || !info) return;
  for (const [place, values] of Object.entries(message.tactile)) drawTactile(place, values);
  // A board that connected after the page loaded: fetch its layout once.
  if (Object.keys(message.tactile).some((place) => !canvases[place])) loadInfo();
  if (message.hand) {
    const range = 120;  // degrees shown full-width; LEAP joints stay within about -60..120
    for (const row of document.querySelectorAll(".joint")) {
      const k = Number(row.dataset.joint);
      const cmd = message.hand.cmd[k], pos = message.hand.pos[k];
      const width = (value) => `${Math.max(0, Math.min(100, ((value ?? 0) + 30) / (range + 30) * 100))}%`;
      row.querySelector(".cmd").style.width = width(cmd);
      row.querySelector(".pos").style.width = pos === null ? "0" : width(pos);
      row.querySelector(".val").textContent = pos === null ? "-" : `${pos.toFixed(0)}°`;
    }
    const mode = HAND_MODES[message.hand.mode] || "?";
    $("hand-mode").textContent = `텔레옵 ${mode}`;
  }
}

function formatTime(seconds) {
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${(seconds - minutes * 60).toFixed(1).padStart(4, "0")}`;
}

function button(label, className, handler) {
  return el("button", { class: `btn ${className}`, type: "button", onclick: handler, text: label });
}

function renderActions(recorder, problems) {
  const box = $("actions");
  const signature = `${recorder.state}:${problems.length > 0}`;
  if (box.dataset.signature === signature) return;   // keep focus: rebuild only on change
  box.dataset.signature = signature;
  box.className = "actions";
  if (recorder.state === "idle") {
    box.replaceChildren(button("녹화 시작", "primary big", actStart));
    if (problems.length) box.append(button("문제를 무시하고 시작", "small", () => actStart(true)));
  } else if (recorder.state === "recording") {
    box.replaceChildren(button("정지", "stop big", actStop), button("표시 남기기", "", actMark),
      button("중단하고 버리기", "small danger", actDiscard));
  } else {
    box.className = "actions three";
    box.replaceChildren(button("성공으로 저장", "ok big", () => actSave(true)),
      button("실패로 저장", "big", () => actSave(false)), button("버리고 다시 찍기", "wide danger", actDiscard));
  }
}

function renderReview(summary) {
  const box = $("review");
  if (!summary) { box.replaceChildren(); return; }
  const rows = [["길이", `${summary.duration_s.toFixed(1)} s`]];
  for (const [name, stream] of Object.entries(summary.streams)) {
    const stats = stream.stats;
    rows.push([name, `${stats.hz.toFixed(0)} Hz · 공백 ${stats.max_gap_ms.toFixed(0)} ms${stats.missed ? ` · 빠짐 ${stats.missed}` : ""}`]);
  }
  const table = el("table", {}, rows.map(([key, value]) => el("tr", {}, [el("td", { text: key }), el("td", { text: value })])));
  const flags = [];
  for (const [name, count] of Object.entries(summary.flags.dropouts)) flags.push(`${name} 끊김 ${count}회`);
  if (summary.flags.forced_start) flags.push("점검 실패 상태에서 강제 시작");
  box.replaceChildren(table, flags.length ? el("p", { class: "flag", text: `주의: ${flags.join(", ")}` }) : null);
}

function onState(message) {
  state = message;
  const recorder = message.recorder;
  $("task-name").textContent = recorder.task;
  $("task-text").textContent = recorder.text;
  $("session-name").textContent = recorder.session || "(첫 녹화 때 생성)";
  $("operator-name").textContent = recorder.operator;
  $("count-ok").textContent = recorder.counts.success;
  $("count-fail").textContent = recorder.counts.failure;
  $("count-total").textContent = recorder.counts.success + recorder.counts.failure;
  $("disk-text").textContent = message.disk_free_gb === null ? "" : `디스크 ${message.disk_free_gb} GB 남음`;

  const ready = recorder.state === "idle" && message.problems.length === 0;
  $("state-card").className = `panel state-card ${recorder.state}${ready ? " ready" : ""}`;
  $("state-label").textContent = recorder.state === "idle" && !ready ? "대기 (준비 안 됨)" : STATE_LABEL[recorder.state];
  $("state-ep").textContent = recorder.state === "idle" ? "" : `ep_${String(recorder.episode).padStart(4, "0")}`;
  const limit = recorder.time_limit_s > 0 ? ` / ${formatTime(recorder.time_limit_s)}` : "";
  $("timer").textContent = formatTime(recorder.elapsed_s) + (recorder.state === "recording" ? limit : "");
  renderActions(recorder, message.problems);
  $("problems").replaceChildren(...message.problems.map((problem) => el("li", { text: problem })));
  renderReview(recorder.summary);

  const rows = [];
  for (const [name, stream] of Object.entries(message.streams)) {
    const history = hzHistory[name] = hzHistory[name] || [];
    history.push(stream.hz);
    if (history.length > 300) history.shift();
    const fault = stream.required && !["ok", "slow"].includes(stream.status);
    rows.push(el("tr", { class: fault ? "fault" : "" }, [
      el("td", { text: name }),
      el("td", { class: "num", text: `${stream.hz.toFixed(0)} / ${stream.nominal_hz.toFixed(0)}` }),
      el("td", { class: "num", text: stream.age_s === null ? "-" : stream.age_s < 1 ? `${(stream.age_s * 1000).toFixed(0)} ms` : `${stream.age_s.toFixed(1)} s` }),
      el("td", { class: "num", text: String(stream.missed) }),
      el("td", {}, [
        el("span", { class: `tag ${stream.status}`, text: STATUS_LABEL[stream.status] || stream.status, title: stream.message }),
        stream.required ? null : el("span", { class: "tag opt", text: "선택", style: "margin-left:4px" }),
      ]),
    ]));
    const camHz = $(`cam-hz-${name}`);
    if (camHz) camHz.textContent = `${stream.hz.toFixed(0)} Hz`;
  }
  $("stream-rows").replaceChildren(...rows);
  if (page === "sensors") renderSensors();
}

const actStart = (force) => command("/api/record/start", { force: force === true });
const actStop = () => command("/api/record/stop");
const actSave = (success) => command("/api/record/save", { success }, success ? "성공으로 저장했습니다" : "실패로 저장했습니다");
const actDiscard = () => command("/api/record/discard", {}, "버렸습니다");
const actMark = () => command("/api/record/mark", { label: "" }, "표시를 남겼습니다");
const actZero = () => command("/api/tactile/zero", {}, "촉각 영점 보정을 요청했습니다");

document.addEventListener("keydown", (event) => {
  if (event.target.matches("input, select, textarea") || event.ctrlKey || event.metaKey || event.altKey) return;
  if (page !== "record" || !state) return;
  const recorderState = state.recorder.state;
  const key = event.key.toLowerCase();
  if (event.code === "Space") {
    event.preventDefault();
    if (recorderState === "idle") actStart(false);
    else if (recorderState === "recording") actStop();
  } else if (recorderState === "review" && key === "s") actSave(true);
  else if (recorderState === "review" && key === "f") actSave(false);
  else if (recorderState !== "idle" && key === "d") actDiscard();
  else if (recorderState === "recording" && key === "m") actMark();
  else if (recorderState === "idle" && key === "z") actZero();
});

// ---- episodes page --------------------------------------------------------------------------

async function loadEpisodes() {
  let data;
  try { data = await api("GET", "/api/episodes"); } catch (error) { toast(error.message, true); return; }
  $("episodes-dir").textContent = data.task_dir;
  $("episodes-empty").hidden = data.episodes.length > 0;
  $("convert-cmd").textContent =
    `tactile-rec convert --config <rig.yaml> --in ${data.task_dir} \\\n    --out <출력 폴더> --repo-id shape_up/${state ? state.recorder.task : "task"}`;
  $("episode-rows").replaceChildren(...data.episodes.map((row) => {
    const notes = [];
    for (const [name, count] of Object.entries(row.dropouts)) notes.push(`${name} 끊김 ${count}`);
    if (row.forced) notes.push("강제 시작");
    const other = row.result === "success" ? "failure" : "success";
    return el("tr", {}, [
      el("td", { text: row.session }),
      el("td", { text: row.episode }),
      el("td", {}, el("span", { class: `tag ${row.result}`, text: row.result === "success" ? "성공" : "실패" })),
      el("td", { class: "num", text: `${Number(row.duration_s).toFixed(1)} s` }),
      el("td", { class: "num", text: `${Number(row.max_gap_ms).toFixed(0)} ms` }),
      el("td", { class: notes.length ? "" : "muted", text: notes.join(", ") || "-" }),
      el("td", {}, [
        button(other === "success" ? "성공으로 변경" : "실패로 변경", "small", async () => {
          try {
            await api("POST", "/api/episodes/label", { session: row.session, episode: row.episode, result: other });
            loadEpisodes();
          } catch (error) { toast(error.message, true); }
        }),
        button("삭제", "small danger", async () => {
          if (!confirm(`${row.session}/${row.episode} 를 삭제합니다. 되돌릴 수 없습니다.`)) return;
          try {
            await api("DELETE", `/api/episodes/${row.session}/${row.episode}`);
            loadEpisodes();
          } catch (error) { toast(error.message, true); }
        }),
      ]),
    ]);
  }));
}

// ---- sensors page ---------------------------------------------------------------------------

function sparkline(canvas, values, nominal) {
  const context = canvas.getContext("2d");
  const { width, height } = canvas;
  context.clearRect(0, 0, width, height);
  const top = Math.max(nominal * 1.2, ...values, 1);
  context.strokeStyle = "#d5d7dc";
  context.beginPath();
  const expected = height - nominal / top * (height - 4) - 2;
  context.moveTo(0, expected); context.lineTo(width, expected); context.stroke();
  context.strokeStyle = "#16181d"; context.lineWidth = 1.5;
  context.beginPath();
  values.forEach((value, index) => {
    const x = index / Math.max(1, values.length - 1) * width;
    const y = height - value / top * (height - 4) - 2;
    if (index) context.lineTo(x, y); else context.moveTo(x, y);
  });
  context.stroke();
}

function renderSensors() {
  if (!state || !info) return;
  const box = $("sensor-cards");
  const cards = [];
  for (const [name, stream] of Object.entries(state.streams)) {
    const spec = info.specs[name] || { fields: {}, meta: {} };
    const canvas = el("canvas", { class: "spark", width: 300, height: 36, role: "img", "aria-label": `${name} 최근 Hz` });
    const pairs = [
      ["Hz (기대)", `${stream.hz.toFixed(1)} (${stream.nominal_hz})`],
      ["받은 수", String(stream.count)], ["빠짐", String(stream.missed)],
      ["필수", stream.required ? "예" : "아니오 (없어도 녹화 가능)"],
      ["원천 시각", spec.src_clock || "-"],
      ["항목", Object.entries(spec.fields).map(([key, field]) => `${key}[${field.shape.join("x")}] ${field.unit}`).join(", ") || "-"],
    ];
    const meta = spec.meta || {};
    if (meta.firmware) pairs.push(["펌웨어", meta.firmware]);
    if (meta.layout) pairs.push(["모듈", meta.layout.modules.map((m) => `${m.name}→${m.place} (${m.points})`).join(", ")]);
    if (meta.model) pairs.push(["모델", `${meta.model} ${meta.usb ? `USB ${meta.usb}` : ""}`]);
    if (meta.joints && stream.kind !== "video") pairs.push(["관절", meta.joints.join(", ")]);
    cards.push(el("div", { class: "panel" }, [
      el("div", { class: "sensor-top" }, [
        el("h2", { text: name }),
        el("span", { class: `tag ${stream.status}`, text: STATUS_LABEL[stream.status] || stream.status }),
      ]),
      canvas,
      el("dl", { class: "kv" }, pairs.flatMap(([key, value]) => [el("dt", { text: key }), el("dd", { text: value })])),
      stream.message ? el("div", { class: "sensor-msg", text: stream.message }) : null,
    ]));
    sparkline(canvas, hzHistory[name] || [], stream.nominal_hz);
  }
  box.replaceChildren(...cards);
}

// ---- settings page --------------------------------------------------------------------------

function renderSettings() {
  if (!info) return;
  $("config-json").textContent = JSON.stringify(info.config, null, 2);
  $("config-source").textContent = info.config.source || "";
  if (state && !$("session-form").dataset.filled) {
    const form = $("session-form");
    form.task.value = state.recorder.task;
    form.operator.value = state.recorder.operator;
    form.text.value = state.recorder.text;
    form.time_limit_s.value = state.recorder.time_limit_s;
    form.dataset.filled = "1";
  }
}

$("session-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.target;
  const result = await command("/api/session", {
    task: form.task.value.trim(), operator: form.operator.value.trim(), text: form.text.value.trim(),
    time_limit_s: Number(form.time_limit_s.value) || 0,
  }, "세션을 바꿨습니다");
  $("session-msg").textContent = result ? `다음 녹화부터 ${result.task_dir} 아래에 저장됩니다.` : "";
});

// ---- navigation -----------------------------------------------------------------------------

function show(name) {
  page = ["record", "episodes", "sensors", "settings"].includes(name) ? name : "record";
  for (const section of document.querySelectorAll(".page")) section.hidden = section.id !== `page-${page}`;
  for (const link of document.querySelectorAll("#nav a")) link.classList.toggle("on", link.dataset.page === page);
  if (page === "episodes") loadEpisodes();
  if (page === "sensors") renderSensors();
  if (page === "settings") renderSettings();
}

window.addEventListener("hashchange", () => show(location.hash.slice(1)));
$("episodes-refresh").addEventListener("click", loadEpisodes);
$("zero-btn").addEventListener("click", actZero);
show(location.hash.slice(1));
// Draw once from a plain request so a page is never empty while the socket connects.
Promise.all([loadInfo(), api("GET", "/api/state").then(onState).catch(() => {})]).then(() => show(page));
connect();
