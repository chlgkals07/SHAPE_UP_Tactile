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
const canvases = {};     // place -> {canvas, graph, range, fz, geometry, history, last}
let unknownPlaces = [];  // tactile places that are not one of the four fingers
let lastInfoLoad = 0;
let lastSensorRender = 0;

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
  // Tiles take the upright picture's own shape (nothing is letterboxed) and share one height.
  const ratios = info.cameras.map((camera) => camera.width / camera.height);
  box.style.setProperty("--sum-aspect", ratios.reduce((sum, ratio) => sum + ratio, 0) || 1);
  box.style.setProperty("--count", info.cameras.length || 1);
  for (const camera of info.cameras) {
    const frame = el("div", { class: "cam-frame", style: `--aspect: ${camera.width} / ${camera.height}` },
      el("img", { src: `/api/stream/${camera.name}`, alt: `${camera.name} 미리보기` }));
    box.append(el("div", { class: "cam", style: `--ratio: ${camera.width / camera.height}` }, [
      frame,
      el("div", { class: "cam-cap" }, [
        el("span", { text: camera.name }),
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
      const canvas = el("canvas", { class: "points", role: "img", "aria-label": `${fingerLabel} ${segmentLabel} 측정점별 수직력` });
      const graph = el("canvas", { class: "series", role: "img", "aria-label": `${fingerLabel} ${segmentLabel} 합력 Fx Fy Fz 추이` });
      const range = el("span", { class: "range" });
      const fz = el("span", { text: sensor ? "0.0" : "-" });
      const pad = el("div", { class: `pad ${segment === "tip" ? "tip" : "seg-pad"}${sensor ? "" : " off"}` }, [
        el("div", { class: "pad-head" }, [
          el("span", { class: "seg", text: sensor ? `${segmentLabel} · ${sensor.points}점` : `${segmentLabel} · 센서 없음` }),
          el("span", { class: "fz" }, [fz, el("small", { text: "N" })]),
        ]),
        canvas,
        el("div", { class: "series-wrap" }, [graph, range]),
      ]);
      column.append(pad);
      if (sensor) {
        canvases[place] = { canvas, graph, range, fz, geometry: geometry(sensor.xyz), history: [], last: null };
        enableRotate(canvas);
      }
    }
    box.append(column);
  }
  // Sensors on places other than the four fingers still record; they are listed, not drawn.
  unknownPlaces = Object.keys(info.tactile).filter((place) => !canvases[place]);
  buildHand();
}

// ---- tactile view: the same picture as paxini_sdk/tools/to_rerun.py ----------------------------
// 3D taxel points at the vendor coordinates. Unloaded points are light grey; loaded points
// follow a blue ramp that is darkest at the chosen full-scale force (3 N by default, as in the
// SDK viewer) and grow with Fz. Under each sensor: resultant Fx / Fy / Fz over the last seconds.

const REST = [210, 215, 220], RAMP_LOW = [230, 241, 251], RAMP_HIGH = [24, 95, 165];
const SERIES = [["Fx", "#8a909b"], ["Fy", "#c9861a"], ["Fz", "rgb(24,95,165)"]];
const HISTORY = 150;                       // resultant samples kept per sensor (about 15 s)
const DEFAULT_VIEW = { yaw: -0.35, pitch: 0.6 };
let view = { ...DEFAULT_VIEW };            // one camera for all sensors; drag to rotate

function fzColour(counts, full) {
  if (counts <= 0) return `rgb(${REST})`;
  const t = Math.min(1, counts / Math.max(1, full));
  return `rgb(${RAMP_LOW.map((low, k) => Math.round(low + (RAMP_HIGH[k] - low) * t))})`;
}

function geometry(xyz) {
  // Centre the points and remember the radius of the sphere that holds them, so the sensor
  // stays the same size on screen while it is rotated.
  const centre = [0, 1, 2].map((k) => (Math.min(...xyz.map((p) => p[k])) + Math.max(...xyz.map((p) => p[k]))) / 2);
  const points = xyz.map((p) => p.map((value, k) => value - centre[k]));
  const reach = Math.max(...points.map((p) => Math.hypot(...p))) || 1;
  return { points, reach };
}

function project([x, y, z]) {
  // Turn about the vertical axis (yaw), then tip the sensor back (pitch). Returns screen x, y
  // (y up) and depth toward the viewer.
  const cy = Math.cos(view.yaw), sy = Math.sin(view.yaw), cp = Math.cos(view.pitch), sp = Math.sin(view.pitch);
  const x1 = x * cy - y * sy, y1 = x * sy + y * cy;
  return [x1, y1 * cp + z * sp, -y1 * sp + z * cp];
}

function fitCanvas(canvas) {
  const ratio = window.devicePixelRatio || 1, width = canvas.clientWidth, height = canvas.clientHeight;
  if (!width || !height) return null;
  if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
    canvas.width = Math.round(width * ratio);   // match the screen pixels: sharp, never stretched
    canvas.height = Math.round(height * ratio);
  }
  const context = canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, width, height);
  return { context, width, height };
}

function drawTactile(place, values) {
  const item = canvases[place];
  if (!item) return;
  item.last = values;
  const fitted = fitCanvas(item.canvas);
  if (!fitted) return;
  const { context, width, height } = fitted;
  const { points, reach } = item.geometry;
  const full = Number($("tactile-scale").value);
  const drawn = points.map((point, index) => [...project(point), values.fz[index] || 0]);
  // Fill the canvas at the current viewing angle, leaving room for the largest dot
  // (1.9 mm radius in sensor units) at every edge.
  const xs = drawn.map((p) => p[0]), ys = drawn.map((p) => p[1]);
  const midX = (Math.min(...xs) + Math.max(...xs)) / 2, midY = (Math.min(...ys) + Math.max(...ys)) / 2;
  const scale = Math.min(
    (width - 8) / (Math.max(...xs) - Math.min(...xs) + 3.8),
    (height - 8) / (Math.max(...ys) - Math.min(...ys) + 3.8),
    (Math.min(width, height) - 8) / reach,           // a flat-on view must not grow without limit
  );
  drawn.sort((p, q) => p[2] - q[2]);                    // far points first
  for (const [x, y, , counts] of drawn) {
    const radius = (0.4 + Math.min(1.5, Math.max(0, counts * 0.05))) * scale;   // SDK rule, in mm
    context.beginPath();
    context.arc(width / 2 + (x - midX) * scale, height / 2 - (y - midY) * scale, Math.max(3, radius), 0, Math.PI * 2);
    context.fillStyle = fzColour(counts, full);
    context.fill();
    context.lineWidth = 0.75;
    context.strokeStyle = counts > 0 ? "rgba(24,95,165,0.55)" : "#aeb4bd";
    context.stroke();
  }
  item.fz.textContent = values.r[2].toFixed(1);
  item.history.push(values.r);
  if (item.history.length > HISTORY) item.history.shift();
  drawSeries(item);
}

function drawSeries(item) {
  const fitted = fitCanvas(item.graph);
  if (!fitted) return;
  const { context, width, height } = fitted;
  const history = item.history;
  // Symmetric range that always shows at least +-1 N, so noise near zero does not fill the plot.
  const peak = Math.max(1, ...history.map((r) => Math.max(Math.abs(r[0]), Math.abs(r[1]), Math.abs(r[2]))));
  const y = (value) => height / 2 - value / peak * (height / 2 - 3);
  context.strokeStyle = "#d9dce1"; context.lineWidth = 1;
  context.beginPath(); context.moveTo(0, y(0)); context.lineTo(width, y(0)); context.stroke();
  SERIES.forEach(([, colour], axis) => {
    context.strokeStyle = colour; context.lineWidth = axis === 2 ? 2 : 1.25;
    context.beginPath();
    history.forEach((r, index) => {
      const x = width - (history.length - 1 - index) / (HISTORY - 1) * width;   // newest at the right
      if (index) context.lineTo(x, y(r[axis])); else context.moveTo(x, y(r[axis]));
    });
    context.stroke();
  });
  item.range.textContent = `±${peak.toFixed(0)} N`;
}

function redrawTactile() {
  for (const [place, item] of Object.entries(canvases)) if (item.last) drawTactile(place, item.last);
}

function enableRotate(canvas) {
  // Drag any sensor to turn all of them together; double-click returns to the default view.
  let start = null;
  canvas.addEventListener("pointerdown", (event) => {
    start = { x: event.clientX, y: event.clientY, ...view };
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!start) return;
    view.yaw = start.yaw + (event.clientX - start.x) * 0.01;
    view.pitch = Math.max(0, Math.min(Math.PI / 2, start.pitch + (event.clientY - start.y) * 0.01));
    redrawTactile();
  });
  const end = () => { start = null; };
  canvas.addEventListener("pointerup", end);
  canvas.addEventListener("pointercancel", end);
  canvas.addEventListener("dblclick", () => { view = { ...DEFAULT_VIEW }; redrawTactile(); });
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
  // A board that connected after the page loaded: fetch its layout, at most every 3 s.
  const fresh = Object.keys(message.tactile).some((place) => !canvases[place] && !unknownPlaces.includes(place));
  if (fresh && Date.now() - lastInfoLoad > 3000) { lastInfoLoad = Date.now(); loadInfo(); }
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
      el("td", { class: "num", text: `${stream.hz.toFixed(0)} / ${stream.nominal_hz.toFixed(0)}`, title: "측정 Hz / 기대 Hz" }),
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
  // Rebuilding the cards on every update makes text impossible to select; once a second is enough.
  if (page === "sensors" && Date.now() - lastSensorRender > 1000) renderSensors();
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
  lastSensorRender = Date.now();
  const box = $("sensor-cards");
  const cards = [];
  for (const [name, stream] of Object.entries(state.streams)) {
    const spec = info.specs[name] || { fields: {}, meta: {} };
    const canvas = el("canvas", { class: "spark", width: 360, height: 44, role: "img", "aria-label": `${name} 최근 Hz` });
    const pairs = [
      ["Hz (기대)", `${stream.hz.toFixed(1)} (${stream.nominal_hz})`],
      ["받은 수", String(stream.count)], ["빠짐", String(stream.missed)],
      ["필수", stream.required ? "예" : "아니오 (없어도 녹화 가능)"],
      ["원천 시각", spec.src_clock || "-"],
      ...(stream.kind === "video" ? [["회전", `${(spec.meta || {}).rotation_deg || 0}° (미리보기와 변환에 적용)`]] : []),
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
