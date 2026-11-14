// Control Hub page. Everything shown comes from /api/describe (the config) and /api/state
// (polled once a second). The page only ever sends ids back.
"use strict";

const $ = (id) => document.getElementById(id);
const LABEL = { off: "꺼짐", starting: "켜는 중", ready: "준비됨", stopping: "끄는 중", done: "끝남", failed: "오류" };
const ALIVE = ["starting", "ready", "stopping"];
const PAGES = ["home", "device", "scan", "run", "logs", "all"];
const WORK_PAGES = ["run", "all"];  // pages with the process detail column
const LEVEL_LABEL = { ok: "정상", warn: "주의", bad: "문제", idle: "꺼짐" };
const FINGERS = [["검지", 0], ["중지", 4], ["약지", 8], ["엄지", 12]];
const MOTOR_HOT_C = 60;  // shown as a warning; tune on the real hand
const INFO_LABEL = {
  path: "경로", by_id: "by-id", serial: "시리얼", usb_id: "USB id", product: "제품",
  speed_mbps: "USB 속도", latency_timer: "latency timer", rw: "읽기·쓰기", bus_path: "버스 위치", ms: "지연",
};
const ERROR_LINE = /\b(error|fatal|traceback|exception|failed|failure|no such file|not found|refused|denied|timed out|unreachable|cannot|abort(ed)?|segmentation fault|killed)\b/i;

let D = null;            // describe
let S = null;            // state
let page = "home";
let pageArg = null;      // device id on the device page
let profileId = localStorage.getItem("hub.profile");
let selected = null;     // process id shown in the detail panel
const flagChoice = {};   // pid -> [flag ids] chosen on this page
const log = { pid: null, run: null, offset: 0, chosen: "", runsFor: null, busy: false };
const logsView = { sid: null, dev: "", level: "", incident: null, file: null, detail: null,
                   sessions: [], events: [], incidents: [], loadedAt: 0, busy: false };
const devEvents = { id: null, list: [], at: 0, busy: false };

// ---------- helpers ----------
function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function setHTML(el, html) {
  // Re-render only on change: replacing a button under the pointer would swallow the click.
  if (el._html !== html) { el.innerHTML = html; el._html = html; }
}
async function api(path, body) {
  const options = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  };
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
  return data;
}
let toastTimer = null;
function toast(message, bad) {
  const el = $("toast");
  el.textContent = message;
  el.className = bad ? "toast bad" : "toast";
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, bad ? 7000 : 2500);
}
function elapsed(since) {
  const s = Math.max(0, Math.round(S.time - since));
  if (s < 60) return `${s}초`;
  if (s < 3600) return `${Math.floor(s / 60)}분 ${s % 60}초`;
  return `${Math.floor(s / 3600)}시간 ${Math.floor((s % 3600) / 60)}분`;
}
function runLabel(run) {
  const m = /^(\d{4})(\d\d)(\d\d)-(\d\d)(\d\d)(\d\d)/.exec(run);
  return m ? `${m[2]}-${m[3]} ${m[4]}:${m[5]}:${m[6]}` : run;
}
const stateOf = (pid) => (S.processes[pid] || { state: "off", issues: [], blockers: [], dependents: [] });
const titleOf = (id) => (D.processes[id] || D.checks[id] || { title: id }).title;
function chosenFlags(pid) {
  const proc = D.processes[pid];
  if (!proc) return [];
  return flagChoice[pid] ?? proc.flags.filter((f) => f.default).map((f) => f.id);
}
function clock(t) {
  const d = new Date(t * 1000);
  return [d.getHours(), d.getMinutes(), d.getSeconds()].map((n) => String(n).padStart(2, "0")).join(":");
}
const devState = (id) => (S.devices && S.devices[id]) || { level: "idle", summary: "" };
function infoValue(key, value) {
  if (key === "rw") return value ? "가능" : "권한 없음";
  if (key === "speed_mbps") return `${value} Mbps`;
  if (key === "ms") return `${value} ms`;
  return Array.isArray(value) ? value.join(", ") : String(value);
}
function notesDone() {
  try { return JSON.parse(localStorage.getItem("hub.notes") || "{}"); } catch { return {}; }
}

// ---------- confirm dialog ----------
function confirmDialog(title, sub, items, okLabel, danger) {
  const dialog = $("confirm");
  $("confirm-title").textContent = title;
  $("confirm-sub").textContent = sub || "";
  $("confirm-items").innerHTML = items.map((text) =>
    `<label><input type="checkbox"><span>${esc(text)}</span></label>`).join("");
  const ok = $("confirm-ok");
  ok.textContent = okLabel;
  ok.className = danger ? "btn stop" : "btn primary";
  const boxes = [...dialog.querySelectorAll("input")];
  const sync = () => { ok.disabled = !boxes.every((b) => b.checked); };
  boxes.forEach((b) => b.addEventListener("change", sync));
  sync();
  return new Promise((resolve) => {
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "ok"), { once: true });
    dialog.returnValue = "cancel";
    dialog.showModal();
  });
}

// ---------- actions ----------
async function act(fn) {
  try { await fn(); } catch (error) { toast(error.message, true); }
  tick();
}
async function startProcess(pid) {
  const proc = D.processes[pid];
  const flags = chosenFlags(pid);
  const items = proc.confirm_start
    .filter((c) => !c.unless_flag || !flags.includes(c.unless_flag)).map((c) => c.text);
  if (items.length) {
    const verb = proc.kind === "tool" ? "실행" : "켜기";
    if (!await confirmDialog(`${proc.title} ${verb}`, `${proc.where} 에서 실행합니다. 모두 확인해야 진행됩니다.`, items, verb)) return;
  }
  select(pid);
  await api(`/api/process/${pid}/start`, { flags, confirmed: items.length > 0 });
}
function stopItems(pid) {
  const proc = D.processes[pid];
  const items = proc ? [...proc.confirm_stop] : [];
  const dependents = stateOf(pid).dependents || [];
  if (dependents.length) items.push(`이것에 기대는 프로세스가 영향을 받는다: ${dependents.map(titleOf).join(", ")}`);
  return items;
}
async function stopProcess(pid) {
  const items = stopItems(pid);
  if (items.length && !await confirmDialog(`${titleOf(pid)} 끄기`, "Ctrl+C 를 보냅니다.", items, "끄기", true)) return;
  await api(`/api/process/${pid}/stop`, { confirmed: items.length > 0 });
}
async function killProcess(pid) {
  const ok = await confirmDialog(`${titleOf(pid)} 강제 종료`, "창을 닫아 프로세스를 바로 끝냅니다. 정리 동작(Torque OFF 등)이 실행되지 않을 수 있습니다.",
    ["Ctrl+C 로 꺼지지 않는 것을 확인했다"], "강제 종료", true);
  if (ok) await api(`/api/process/${pid}/kill`, {});
}
async function stopAll() {
  const profile = D.profiles.find((p) => p.id === profileId);
  const ordered = profile ? profile.steps.filter((s) => s.process).map((s) => s.process) : [];
  const running = Object.keys(S.processes).filter((pid) => ALIVE.includes(stateOf(pid).state));
  running.sort((a, b) => ordered.indexOf(b) - ordered.indexOf(a)); // reverse of the start order
  if (!running.length) { toast("켜져 있는 프로세스가 없습니다"); return; }
  const items = running.flatMap((pid) => (D.processes[pid]?.confirm_stop || []).map((t) => `${titleOf(pid)}: ${t}`));
  if (!items.length) items.push("전부 꺼도 된다");
  if (!await confirmDialog("전체 끄기", `이 순서로 하나씩 끕니다: ${running.map(titleOf).join(" → ")}`, items, "전체 끄기", true)) return;
  for (const pid of running) {
    try { await api(`/api/process/${pid}/stop`, { confirmed: true }); } catch (error) { toast(error.message, true); continue; }
    const grace = (D.processes[pid]?.stop_grace_s || 10) * 1000 + 2000;
    const until = Date.now() + grace;
    while (Date.now() < until) {
      await new Promise((r) => setTimeout(r, 400));
      await tick();
      if (!ALIVE.includes(stateOf(pid).state)) break;
    }
    if (ALIVE.includes(stateOf(pid).state)) {
      toast(`${titleOf(pid)} 이(가) 꺼지지 않아 여기서 멈춥니다. 확인 후 강제 종료하거나 다시 누릅니다.`, true);
      select(pid);
      return;
    }
  }
  toast("전부 껐습니다");
}

// ---------- rendering: rows ----------
function rowSub(pid, proc, st) {
  const issue = st.issues && st.issues.length ? st.issues[st.issues.length - 1] : null;
  if (st.state === "failed") {
    const why = issue ? (issue.hint || issue.line) : (st.last_line || "");
    return ["bad", `종료 코드 ${st.exit_code ?? "?"}${why ? " · " + why : ""}`];
  }
  if (st.state === "stopping") return ["warn", st.stop_overdue ? "Ctrl+C 에 반응이 없습니다" : "Ctrl+C 를 보냈습니다"];
  if (st.state === "starting") return ["warn", proc && proc.ready ? `기다리는 중: ${proc.ready}` : "켜는 중"];
  if (st.state === "ready") {
    const up = st.started_at ? `켜진 지 ${elapsed(st.started_at)}` : "켜져 있음";
    if (st.stale_config) return ["warn", `${up} · 설정이 바뀜, 다시 켜야 적용`];
    return issue ? ["warn", `${up} · 로그에 문제 ${st.issues.length}건`] : ["", up];
  }
  if (st.state === "done") return ["", "정상적으로 끝남"];
  if (st.blockers && st.blockers.length) return ["warn", st.blockers.join(" / ")];
  return ["", proc ? proc.help.split("\n")[0] : "설정에 없는 프로세스"];
}
function rowButton(pid, proc, st) {
  if (!proc && !ALIVE.includes(st.state)) return "";
  if (st.state === "stopping") {
    return st.stop_overdue
      ? `<button class="btn small stop" data-action="kill" data-id="${pid}">강제 종료</button>`
      : `<button class="btn small" disabled>끄는 중</button>`;
  }
  if (ALIVE.includes(st.state)) return `<button class="btn small danger" data-action="stop" data-id="${pid}">끄기</button>`;
  const blocked = st.blockers && st.blockers.length;
  const verb = proc.kind === "tool" ? "실행" : "켜기";
  return `<button class="btn small primary" data-action="start" data-id="${pid}" ${blocked ? "disabled" : ""}>${verb}</button>`;
}
function processRow(pid, num, extra) {
  const proc = D.processes[pid];
  const st = stateOf(pid);
  const [subClass, sub] = rowSub(pid, proc, st);
  const classes = ["row", pid === selected ? "selected" : "", st.state === "failed" ? "failed" : "", extra || ""].join(" ");
  return `<li class="${classes}" data-action="select" data-id="${pid}" tabindex="0">
    <span class="num">${num ?? ""}</span>
    <span class="title"><span class="dot ${st.state}"></span><span class="name">${esc(proc ? proc.title : pid)}</span>
      ${proc && proc.remote ? '<span class="where">Robot PC</span>' : ""}
      <span class="tag ${st.state}">${LABEL[st.state]}</span></span>
    ${rowButton(pid, proc, st)}
    <span class="sub ${subClass}">${esc(sub)}</span>
  </li>`;
}

function renderRun() {
  setHTML($("profile-tabs"), D.profiles.map((p) =>
    `<button class="${p.id === profileId ? "on" : ""}" data-action="profile" data-id="${p.id}">${esc(p.title)}</button>`).join(""));
  const profile = D.profiles.find((p) => p.id === profileId);
  if (!profile) { setHTML($("steps"), '<li class="empty muted">설정에 실행표(profiles)가 없습니다. 전체 페이지를 씁니다.</li>'); return; }
  setHTML($("profile-help"), esc(profile.help));
  const done = notesDone();
  let nextFound = false;
  const html = profile.steps.map((step, i) => {
    if (step.note !== null && step.note !== undefined) {
      const key = `${profile.id}:${i}`;
      const checked = Boolean(done[key]);
      const isNext = !checked && !nextFound;
      if (isNext) nextFound = true;
      return `<li class="row note ${checked ? "checked" : ""} ${isNext ? "next" : ""}">
        <span class="num">${i + 1}</span>
        <label><input type="checkbox" data-note="${key}" ${checked ? "checked" : ""}><span>${esc(step.note)}</span></label></li>`;
    }
    const state = stateOf(step.process).state;
    const isNext = !nextFound && !["ready", "done"].includes(state);
    if (isNext) nextFound = true;
    return processRow(step.process, i + 1, isNext && state !== "starting" ? "next" : "");
  }).join("");
  setHTML($("steps"), html);
}

function renderAll() {
  const orphans = Object.keys(S.processes).filter((pid) => !D.processes[pid]);
  let html = D.groups.map((group) => `<div class="group"><h2>${esc(group)}</h2><ol class="steps">${
    Object.values(D.processes).filter((p) => p.group === group).map((p) => processRow(p.id)).join("")}</ol></div>`).join("");
  if (orphans.length) {
    html += `<div class="group"><h2>설정에 없지만 돌고 있음</h2><ol class="steps">${orphans.map((pid) => processRow(pid)).join("")}</ol></div>`;
  }
  setHTML($("groups"), html);
}

// ---------- rendering: detail ----------
function select(pid) {
  if (selected === pid) return;
  selected = pid;
  log.pid = pid; log.run = null; log.offset = 0; log.chosen = ""; log.runsFor = null;
  const proc = D.processes[pid];
  $("detail").innerHTML = `<div class="panel detail-card">
    <div id="d-top"></div>
    <div class="log-head"><h3>로그</h3>
      <select id="run-select" aria-label="볼 실행"></select>
      <label class="right"><input type="checkbox" id="follow" checked>새 줄 따라가기</label></div>
    <pre class="log" id="log" tabindex="0"></pre>
    <form class="input-row" id="input-form" ${proc && proc.input ? "" : "hidden"}>
      <input type="text" id="input-text" placeholder="프로세스에 보낼 한 줄 (비워 두면 Enter 만)" autocomplete="off">
      <button class="btn small primary">보내기</button></form>
    <div class="attach">터미널에서 직접 보기: <code>${esc(D.attach)}</code> 후 <code>Ctrl+b w</code> 로 창 선택</div>
  </div>`;
  $("detail")._html = null;
  render();
  pollLog();
}
function renderDetail() {
  if (!selected || !$("d-top")) {
    setHTML($("detail"), '<div class="panel empty muted">왼쪽에서 항목을 누르면 명령, 상태, 로그가 여기에 나옵니다.</div>');
    return;
  }
  const pid = selected;
  const proc = D.processes[pid];
  const st = stateOf(pid);
  const alive = ALIVE.includes(st.state);
  const flags = chosenFlags(pid);
  const meta = [];
  if (proc) meta.push(`위치: ${proc.where}`, proc.kind === "tool" ? "도구 (한 번 실행)" : "서비스 (계속 실행)");
  if (st.started_at && st.state !== "off") meta.push(alive ? `켜진 지 ${elapsed(st.started_at)}` : `시작 ${new Date(st.started_at * 1000).toLocaleTimeString("ko-KR")}`);
  if (st.exit_code !== null && st.exit_code !== undefined) meta.push(`종료 코드 ${st.exit_code}`);

  let html = `<div class="detail-top"><span class="dot ${st.state}"></span><h2>${esc(proc ? proc.title : pid)}</h2>
    <span class="tag ${st.state}">${LABEL[st.state]}</span><code class="right muted">${esc(pid)}</code></div>
    <div class="meta">${meta.map((m) => `<span>${esc(m)}</span>`).join("")}</div>`;
  if (!proc) html += '<div class="notice warn">설정 파일에서 빠진 프로세스입니다. 아직 돌고 있어서 끌 수 있게 남겨 두었습니다.</div>';
  if (proc && proc.help) html += `<p class="help">${esc(proc.help)}</p>`;
  if (!alive && st.blockers && st.blockers.length) {
    html += `<div class="notice warn"><b>지금은 켤 수 없습니다</b><ul>${st.blockers.map((b) => `<li>${esc(b)}</li>`).join("")}</ul></div>`;
  }
  if (st.state === "starting" && proc && proc.ready) html += `<div class="notice warn">준비 조건: ${esc(proc.ready)}</div>`;
  if (st.stale_config) html += '<div class="notice warn">설정 파일의 명령이 켤 때와 달라졌습니다. 껐다 켜야 적용됩니다.</div>';
  if (st.state === "stopping" && st.stop_overdue) html += '<div class="notice bad">Ctrl+C 를 보냈지만 끝나지 않았습니다. 로그를 보고, 필요하면 강제 종료합니다.</div>';
  if (proc && proc.flags.length) {
    html += `<div class="flags">${proc.flags.map((f) =>
      `<label><input type="checkbox" data-flag="${f.id}" ${flags.includes(f.id) ? "checked" : ""} ${alive ? "disabled" : ""}>${esc(f.label)} <code class="muted">${esc(f.arg)}</code></label>`).join("")}</div>`;
  }
  const buttons = [];
  const verb = proc && proc.kind === "tool" ? "실행" : "켜기";
  if (proc && !alive) buttons.push(`<button class="btn primary" data-action="start" data-id="${pid}" ${st.blockers.length ? "disabled" : ""}>${st.state === "off" ? verb : "다시 " + verb}</button>`);
  if (alive) buttons.push(`<button class="btn danger" data-action="stop" data-id="${pid}">${st.state === "stopping" ? "Ctrl+C 다시 보내기" : "끄기 (Ctrl+C)"}</button>`);
  if (st.state === "stopping") buttons.push(`<button class="btn stop" data-action="kill" data-id="${pid}">강제 종료</button>`);
  if (["done", "failed"].includes(st.state)) buttons.push(`<button class="btn" data-action="clear" data-id="${pid}">닫기</button>`);
  html += `<div class="actions">${buttons.join("")}</div>`;

  if (st.issues && st.issues.length) {
    html += `<div class="issues"><h3>로그에서 찾은 문제 ${st.issues.length}건 (최근 것이 아래)</h3><ul>${st.issues.map((issue) =>
      `<li><div class="line">${esc(issue.line)}${issue.count > 1 ? ` <b>×${issue.count}</b>` : ""}</div>${issue.hint ? `<div class="hint">${esc(issue.hint)}</div>` : ""}</li>`).join("")}</ul></div>`;
  }
  if (proc) {
    const flagArgs = proc.flags.filter((f) => flags.includes(f.id)).map((f) => f.arg).join(" ");
    const lines = [...proc.env_lines, proc.cmd + (flagArgs ? " " + flagArgs : "")];
    const related = [];
    if (proc.requires.length) related.push(`먼저 필요: ${proc.requires.map((r) => r.title).join(", ")}`);
    if (proc.conflicts.length) related.push(`같이 켤 수 없음: ${proc.conflicts.map((r) => r.title).join(", ")}`);
    html += `<details ${alive ? "" : "open"}><summary>실행하는 명령 (${esc(proc.where)})</summary><pre>${esc(lines.join("\n"))}</pre>
      ${st.command ? `<pre title="실제로 창에서 실행된 한 줄">${esc(st.command)}</pre>` : ""}
      ${related.length ? `<p class="muted" style="margin-top:6px">${esc(related.join(" · "))}</p>` : ""}</details>`;
  }
  setHTML($("d-top"), html);
}

// ---------- rendering: frame ----------
function renderNav() {
  setHTML($("nav-devices"), Object.values(D.devices).map((d) => {
    const on = page === "device" && pageArg === d.id;
    return `<a href="#device/${d.id}" class="sub ${on ? "on" : ""}" data-page="device" data-arg="${d.id}">
      <span class="dot ${devState(d.id).level}"></span>${esc(d.title)}</a>`;
  }).join(""));
  document.querySelectorAll("#nav > a").forEach((a) => a.classList.toggle("on", a.dataset.page === page));
  const failed = Object.keys(S.processes).filter((pid) => stateOf(pid).state === "failed");
  setHTML(document.querySelector('#nav > a[data-page="all"]'),
    `전체${failed.length ? `<span class="count">${failed.length}</span>` : ""}`);
  const banner = $("failed-banner");
  banner.hidden = !failed.length;
  setHTML(banner, failed.length ? "오류로 끝난 프로세스: " + failed.map((pid) =>
    `<a href="#" data-action="select" data-id="${pid}">${esc(titleOf(pid))}</a>`).join(", ") + " (눌러서 로그 보기)" : "");
  document.title = failed.length ? `(${failed.length}) Control Hub` : "Control Hub";
  const error = $("config-error");
  error.hidden = !S.config_error;
  error.textContent = S.config_error ? `설정 파일 오류 (이전 설정으로 동작 중)\n${S.config_error}` : "";
}
function checkDot(r) {
  if (r.ok === null || r.ok === undefined) return "wait";
  if (!r.ok) return "bad";
  return r.warn ? "warn" : "ok";
}
function renderRail() {
  const checks = Object.values(D.checks).map((c) => {
    const r = S.checks[c.id] || { ok: null, detail: "" };
    const note = r.info && r.info.ms !== undefined ? `${r.info.ms} ms` : r.ok === false ? r.detail : "";
    return `<li title="${esc(c.help)}"><span class="dot ${checkDot(r)}"></span><span class="name">${esc(c.title)}</span>
      <small class="${r.ok === false ? "bad" : ""}">${esc(note)}</small>${r.warn ? `<div class="warnline">${esc(r.warn)}</div>` : ""}</li>`;
  }).join("");
  const services = Object.values(D.processes).filter((p) => p.kind !== "tool");
  const running = services.filter((p) => ALIVE.includes(stateOf(p.id).state)).length;
  const problems = (S.problems || []).filter((e) => S.time - e.t <= 60);
  setHTML($("rail"), `<h3>상태</h3><ul class="rail-checks">${checks}</ul>
    <div class="rail-sum"><span>프로세스 ${running}/${services.length} 실행 중</span>
      <a href="#logs" data-page="logs" class="${problems.some((e) => e.level === "bad") ? "bad" : ""}">최근 1분 문제 ${problems.length} ▸</a></div>`);
}

// ---------- rendering: home ----------
function deviceLine(d) {
  const st = devState(d.id);
  if (st.summary) return st.summary;
  for (const cid of d.checks) {
    const r = S.checks[cid];
    if (r && r.ok) return r.info && r.info.ms !== undefined ? `${D.checks[cid].title} ${r.info.ms} ms` : r.detail;
  }
  const alive = [...d.processes, ...d.tools].filter((pid) => ALIVE.includes(stateOf(pid).state));
  return alive.length ? alive.map(titleOf).join(", ") : LEVEL_LABEL[st.level];
}
function problemRow(e) {
  const dev = e.dev ? D.devices[e.dev] : null;
  const tool = dev && dev.tools[0];
  let open = "";
  if (e.data.incident) open = `data-action="incident" data-id="${esc(e.data.incident)}"`;
  else if (e.data.pid) open = `data-action="jump" data-id="${e.data.pid}" data-run="${esc(e.data.run || "")}"`;
  return `<li class="problem ${e.level}" ${open}><span class="time">${clock(e.t)}</span>
    <span class="dev">${esc(dev ? dev.title : "기타")}</span>
    <span class="text">${esc(e.text)}${e.data.count > 1 ? ` <b>×${e.data.count}</b>` : ""}${e.data.hint ? `<small>→ ${esc(e.data.hint)}</small>` : ""}</span>
    ${tool && e.level === "bad" ? `<button class="btn small" data-action="start" data-id="${tool}">▸ ${esc(titleOf(tool))}</button>` : ""}</li>`;
}
function renderHome() {
  const tiles = Object.values(D.devices).map((d) => {
    const level = devState(d.id).level;
    return `<a class="tile ${level}" href="#device/${d.id}" data-page="device" data-arg="${d.id}">
      <div class="tile-head"><span class="dot ${level}"></span><b>${esc(d.title)}</b><span class="tag ${level}">${LEVEL_LABEL[level]}</span></div>
      <small>${esc(deviceLine(d))}</small></a>`;
  }).join("");
  const shown = Object.keys(S.processes).filter((pid) => [...ALIVE, "failed"].includes(stateOf(pid).state));
  const chips = shown.map((pid) => `<button class="chip" data-action="select" data-id="${pid}">
    <span class="dot ${stateOf(pid).state}"></span>${esc(titleOf(pid))}</button>`).join("");
  const problems = (S.problems || []).map(problemRow).join("");
  setHTML($("page-home"), `<header class="bar"><h1>홈</h1><span class="muted right">세션 ${esc(S.session || "")}</span></header>
    <div class="tiles">${tiles}</div>
    <div class="panel"><div class="panel-head"><h2>프로세스</h2></div>
      <div class="chips">${chips || '<span class="muted">켜진 프로세스가 없습니다. 실행표에서 켭니다.</span>'}</div></div>
    <div class="panel"><div class="panel-head"><h2>최근 문제</h2><a class="right" href="#logs" data-page="logs">전체 기록 ▸</a></div>
      <ul class="problems">${problems || '<li class="muted">문제가 없습니다</li>'}</ul></div>`);
}

// ---------- rendering: device ----------
function checkCard(cid) {
  const c = D.checks[cid];
  const r = S.checks[cid] || { ok: null, detail: "확인 중", info: {} };
  const info = Object.entries(r.info || {}).filter(([k, v]) => INFO_LABEL[k] && v !== null && v !== "" && !(Array.isArray(v) && !v.length));
  const link = c.link && r.ok ? ` <a href="${esc(c.target)}" target="_blank" rel="noopener">${esc(c.link)}</a>` : "";
  return `<div class="check-card ${checkDot(r)}"><div class="check-head"><span class="dot ${checkDot(r)}"></span><b>${esc(c.title)}</b>
      <span class="muted">${esc(r.detail || "")}</span>${link}</div>
    ${info.length ? `<dl>${info.map(([k, v]) => `<dt>${INFO_LABEL[k]}</dt><dd>${esc(infoValue(k, v))}</dd>`).join("")}</dl>` : ""}
    ${r.warn ? `<div class="notice warn">${esc(r.warn)}</div>` : ""}
    ${r.ok === false && c.help ? `<div class="notice bad">${esc(c.help)}</div>` : ""}</div>`;
}
function toolResult(result) {
  if (!result) return '<p class="muted">아직 이 장치의 확인 도구를 돌리지 않았습니다.</p>';
  return `<div class="meta"><span>${esc(titleOf(result.pid))}</span><span>${clock(result.t)}</span>
    <span>종료 코드 ${result.exit_code ?? "?"}</span></div><pre class="tool-out">${esc(result.tail)}</pre>`;
}
function motorCell(index, d, table, fromLog) {
  const m = table ? table.motors[index] : null;
  const seen = fromLog[index] || fromLog[String(index)];
  let cls = "";
  if (m && m.responded) cls = m.hw_err ? "bad" : m.temp >= MOTOR_HOT_C ? "warn" : "ok";
  if ((m && m.responded === false) || seen) cls = "bad";
  const lines = [];
  if (m && m.responded) {
    lines.push([[m.pos, "°"], [m.temp, "°C"], [m.volt, " V"]].filter(([v]) => v !== null)
      .map(([v, unit]) => v + unit).join(" · "));
  }
  if (m && m.hw_err) lines.push(`오류 비트 ${m.hw_err}`);
  if (m && m.responded === false) lines.push("응답 없음");
  if (seen) lines.push(`${clock(seen.t)} ${seen.text}`);
  return `<td class="motor ${cls}"><div class="mid">ID ${m ? m.id : index}</div>
    <div class="joint">${esc(d.joints[index] || "")}</div>${lines.map((l) => `<div>${esc(l)}</div>`).join("")}</td>`;
}
function motorTable(d, st) {
  const result = st.check;
  const table = result && result.table;
  const tool = d.tools[0];
  const rows = FINGERS.map(([finger, start]) =>
    `<tr><th>${finger}</th>${[0, 1, 2, 3].map((k) => motorCell(start + k, d, table, st.motors || {})).join("")}</tr>`).join("");
  const how = tool ? `아래에서 "${titleOf(tool)}"을 실행하면 모터별 값이 채워집니다` : "";
  return `<div class="panel-head"><h2>모터</h2>
      <span class="muted">${table ? `${esc(titleOf(result.pid))} ${clock(result.t)} 결과` : esc(how)}</span></div>
    <table class="motors">${rows}</table>
    ${result && !table ? toolResult(result) : ""}`;
}
async function loadDevEvents(id) {
  if (devEvents.busy || !S.session) return;
  devEvents.busy = true;
  try {
    const { events } = await api(`/api/sessions/${S.session}/events?dev=${encodeURIComponent(id)}`);
    Object.assign(devEvents, { id, list: events.slice(-50).reverse(), at: Date.now() });
    render();
  } catch { /* shown as empty; the state poll reports a lost connection */ } finally { devEvents.busy = false; }
}
function renderDevice(id) {
  const d = D.devices[id];
  const st = devState(id);
  if (devEvents.id !== id || Date.now() - devEvents.at > 3000) loadDevEvents(id);
  const events = devEvents.id === id ? devEvents.list : [];
  const procs = [...d.processes, ...d.tools];
  const recorder = d.recorder_stream.length
    ? `<p class="muted">녹화기 스트림: ${esc(d.recorder_stream.join(", "))}. 실시간 값과 영상은 녹화기 화면에서 봅니다.</p>` : "";
  setHTML($("page-device"), `<header class="bar"><span class="dot ${st.level}"></span><h1>${esc(d.title)}</h1>
      <span class="tag ${st.level}">${LEVEL_LABEL[st.level]}</span><span class="muted">${esc(st.summary)}</span></header>
    ${d.help ? `<p class="help">${esc(d.help)}</p>` : ""}${recorder}
    <div class="panel"><div class="panel-head"><h2>연결</h2></div>
      ${d.checks.map(checkCard).join("") || '<p class="muted">이 장치에 걸린 점검이 없습니다.</p>'}</div>
    ${d.kind === "leap" ? `<div class="panel">${motorTable(d, st)}</div>`
      : `<div class="panel"><div class="panel-head"><h2>마지막 확인 결과</h2></div>${toolResult(st.check)}</div>`}
    <div class="panel"><div class="panel-head"><h2>프로세스와 도구</h2></div>
      ${procs.length ? `<ol class="steps">${procs.map((pid) => processRow(pid)).join("")}</ol>` : '<p class="muted">없음</p>'}</div>
    <div class="panel"><div class="panel-head"><h2>이 장치의 기록</h2><span class="muted">현재 세션, 최신 50개</span></div>
      <ul class="problems">${events.map(problemRow).join("") || '<li class="muted">기록이 없습니다</li>'}</ul></div>`);
}

// ---------- rendering: discovery ----------
function renderScan() {
  const scan = S.scan || { devices: [], misplaced: [] };
  const rows = scan.devices.map((u) => `<tr><td><b>${esc(u.label || u.product || u.usb_id)}</b>
      <div class="muted">${esc([u.manufacturer, u.product].filter(Boolean).join(" "))}</div></td>
    <td class="mono">${esc(u.usb_id)}</td><td class="mono">${esc(u.serial)}</td>
    <td>${u.speed_mbps ? `${u.speed_mbps} Mbps` : ""}</td>
    <td class="mono">${esc([...u.ttys, ...u.videos].join(", "))}${u.by_id.length ? `<div class="muted">${esc(u.by_id.join(", "))}</div>` : ""}</td>
    <td class="mono">${esc(u.bus_path)}</td></tr>`).join("");
  setHTML($("page-scan"), `<header class="bar"><h1>장치 탐색</h1>
      <span class="muted">지금 꽂힌 USB 장치입니다. 보여 주기만 합니다 (포트 자동 지정은 추후).</span></header>
    ${scan.misplaced.map((m) => `<div class="notice warn">${esc(m.text)} (설정: ${esc(m.expected)})</div>`).join("")}
    <div class="panel"><table><tr><th>장치</th><th>vendor:product</th><th>시리얼</th><th>속도</th><th>포트</th><th>버스</th></tr>
      ${rows || '<tr><td colspan="6" class="muted">USB 장치가 없습니다</td></tr>'}</table></div>`);
}

// ---------- rendering: session log and incidents ----------
async function loadLogs(force) {
  if (logsView.busy || (!force && Date.now() - logsView.loadedAt < 3000)) return;
  logsView.busy = true;
  try {
    const { current, sessions } = await api("/api/sessions");
    if (!sessions.some((s) => s.id === logsView.sid)) logsView.sid = current;
    const sid = logsView.sid;
    const query = new URLSearchParams();
    if (logsView.dev) query.set("dev", logsView.dev);
    if (logsView.level) query.set("level", logsView.level);
    const [{ events }, { incidents }] = await Promise.all([
      api(`/api/sessions/${sid}/events?${query}`), api(`/api/sessions/${sid}/incidents`)]);
    Object.assign(logsView, { sessions, events: events.reverse(), incidents, loadedAt: Date.now() });
    logsView.detail = logsView.incident
      ? await api(`/api/sessions/${sid}/incidents/${encodeURIComponent(logsView.incident)}`) : null;
  } catch (error) { toast(error.message, true); } finally { logsView.busy = false; }
  render();
}
function incidentView() {
  const detail = logsView.detail;
  if (!detail) return '<div class="panel empty muted">사고를 누르면 내용이 여기에 나옵니다.</div>';
  const names = Object.keys(detail.files);
  if (!names.includes(logsView.file)) logsView.file = names[0] || null;
  const href = `/api/sessions/${logsView.sid}/export?incident=${encodeURIComponent(logsView.incident)}`;
  return `<div class="panel"><div class="panel-head"><h2>사고</h2><a class="btn small right" href="${href}">zip 받기</a></div>
    <pre class="summary">${esc(detail.summary)}</pre>
    <div class="tabs files">${names.map((n) => `<button class="${n === logsView.file ? "on" : ""}" data-action="file" data-id="${esc(n)}">${esc(n)}</button>`).join("")}</div>
    ${logsView.file ? `<pre class="log">${esc(detail.files[logsView.file])}</pre>` : ""}</div>`;
}
function renderLogs() {
  loadLogs(false);
  const v = logsView;
  const options = (items, chosen, all) => `<option value="">${all}</option>` +
    items.map(([value, label]) => `<option value="${esc(value)}" ${value === chosen ? "selected" : ""}>${esc(label)}</option>`).join("");
  const sessions = v.sessions.map((s) => `<option value="${s.id}" ${s.id === v.sid ? "selected" : ""}>${s.id}${s.id === S.session ? " (현재)" : ""} · 사고 ${s.incidents}</option>`).join("");
  const incidents = v.incidents.map((i) => `<li class="problem bad ${i.id === v.incident ? "on" : ""}" data-action="incident" data-id="${esc(i.id)}">
      <span class="time">${clock(i.t)}</span><span class="dev">${esc(i.dev ? (D.devices[i.dev] || { title: i.dev }).title : "기타")}</span>
      <span class="text">${esc(i.text)}${i.count > 1 ? ` <b>×${i.count}</b>` : ""}</span></li>`).join("");
  setHTML($("page-logs"), `<header class="bar"><h1>로그</h1>
      <select id="logs-sid" aria-label="세션">${sessions}</select>
      <button class="btn small" data-action="new-session">새 세션</button>
      <a class="btn small" href="/api/sessions/${v.sid}/export">세션 zip</a>
      <select id="logs-dev" class="right" aria-label="장치">${options(Object.values(D.devices).map((d) => [d.id, d.title]), v.dev, "모든 장치")}</select>
      <select id="logs-level" aria-label="수준">${options([["bad", "문제"], ["warn", "주의"], ["info", "정보"]], v.level, "모든 수준")}</select></header>
    <div class="logs-grid"><div>
      <div class="panel"><div class="panel-head"><h2>사고 ${v.incidents.length}</h2><span class="muted">오류마다 로그와 상태를 모은 폴더</span></div>
        <ul class="problems">${incidents || '<li class="muted">사고가 없습니다</li>'}</ul></div>
      <div class="panel"><div class="panel-head"><h2>사건</h2><span class="muted">최신이 위</span></div>
        <ul class="problems">${v.events.map(problemRow).join("") || '<li class="muted">사건이 없습니다</li>'}</ul></div>
    </div>${incidentView()}</div>`);
}
function openIncident(id) {
  Object.assign(logsView, { incident: id, file: null, sid: page === "logs" ? logsView.sid : S.session });
  setPage("logs");
}
function jumpToLog(pid, run) {  // that run's whole log, held still; error lines show in red
  setPage("all");
  select(pid);
  Object.assign(log, { chosen: run || "", run: null, offset: 0 });
  $("follow").checked = false;
}

// ---------- log ----------
function appendLog(text) {
  const pre = $("log");
  if (!pre || !text) return;
  const fragment = document.createDocumentFragment();
  const lines = text.split("\n");
  lines.forEach((line, i) => {
    const piece = i < lines.length - 1 ? line + "\n" : line;
    if (!piece) return;
    const cls = line.startsWith("$ ") ? "cmd" : ERROR_LINE.test(line) ? "err" : "";
    if (cls) {
      const span = document.createElement("span");
      span.className = cls;
      span.textContent = piece;
      fragment.appendChild(span);
    } else {
      fragment.appendChild(document.createTextNode(piece));
    }
  });
  pre.appendChild(fragment);
  while (pre.childNodes.length > 5000) pre.removeChild(pre.firstChild);
  if ($("follow").checked) pre.scrollTop = pre.scrollHeight;
}
async function pollLog() {
  if (!selected || log.busy || !$("log")) return;
  log.busy = true;
  const pid = selected;
  try {
    const asked = log.offset;
    const query = `offset=${asked}` + (log.chosen ? `&run=${encodeURIComponent(log.chosen)}` : "");
    const res = await api(`/api/process/${pid}/log?${query}`);
    if (pid !== selected) return;
    if (res.run !== log.run) {       // a new run started (or first load): begin from its top
      log.run = res.run;
      $("log").textContent = "";
      if (asked !== 0) { log.offset = 0; log.busy = false; return pollLog(); }
    }
    log.offset = res.offset;
    appendLog(res.text);
    const current = stateOf(pid).run || "";
    if (log.runsFor !== pid + current) {
      log.runsFor = pid + current;
      const { runs } = await api(`/api/process/${pid}/runs`);
      $("run-select").innerHTML = '<option value="">현재 / 가장 최근 실행</option>' +
        runs.map((run) => `<option value="${esc(run)}" ${run === log.chosen ? "selected" : ""}>${esc(runLabel(run))}</option>`).join("");
    }
  } catch { /* the state poll reports a lost connection */ } finally { log.busy = false; }
}

// ---------- main loop ----------
function render() {
  if (!D || !S) return;
  PAGES.forEach((p) => { $(`page-${p}`).hidden = page !== p; });
  $("work").hidden = !WORK_PAGES.includes(page);
  renderNav();
  renderRail();
  if (page === "home") renderHome();
  else if (page === "device") renderDevice(pageArg);
  else if (page === "scan") renderScan();
  else if (page === "logs") renderLogs();
  else if (page === "run") renderRun();
  else if (page === "all") renderAll();
  if (WORK_PAGES.includes(page)) renderDetail();
}
let knownLoad = null;
async function tick() {
  try {
    const state = await api("/api/state");
    if (!D || knownLoad !== state.loaded_at) {
      D = await api("/api/describe");
      knownLoad = state.loaded_at;
      if (!D.profiles.some((p) => p.id === profileId)) profileId = D.profiles[0]?.id || null;
    }
    S = state;
    $("conn-dot").className = "dot ok";
    $("conn-text").textContent = "hub 연결됨";
    render();
  } catch (error) {
    $("conn-dot").className = "dot bad";
    $("conn-text").textContent = "hub 와 끊김 (프로세스는 tmux 에서 계속 돕니다)";
  }
}
function setPage(next, arg) {
  page = PAGES.includes(next) ? next : "home";
  pageArg = null;
  if (page === "device") {
    pageArg = D && D.devices[arg] ? arg : null;
    if (!pageArg) page = "home";
  }
  const hash = "#" + page + (pageArg ? "/" + pageArg : "");
  if (location.hash !== hash) history.pushState(null, "", hash);
  if (page === "logs") loadLogs(true);
  render();
}

document.addEventListener("click", (event) => {
  const target = event.target.closest("[data-action]");
  if (!target) return;
  const { action, id } = target.dataset;
  if (target.tagName === "A") event.preventDefault();
  if (action === "start") { event.stopPropagation(); act(() => startProcess(id)); }
  else if (action === "stop") act(() => stopProcess(id));
  else if (action === "kill") act(() => killProcess(id));
  else if (action === "clear") act(() => api(`/api/process/${id}/clear`, {}));
  else if (action === "profile") { profileId = id; localStorage.setItem("hub.profile", id); render(); }
  else if (action === "select") {
    if (event.target.closest("button") && event.target.closest("button") !== target) return;
    if (!WORK_PAGES.includes(page)) setPage("all");
    select(id);
    render();
  }
  else if (action === "incident") openIncident(id);
  else if (action === "jump") jumpToLog(id, target.dataset.run);
  else if (action === "file") { logsView.file = id; render(); }
  else if (action === "new-session") act(async () => { await api("/api/sessions/new", {}); logsView.sid = null; await loadLogs(true); });
});
document.addEventListener("click", (event) => {
  const link = event.target.closest("a[data-page]");
  if (!link) return;
  event.preventDefault();
  setPage(link.dataset.page, link.dataset.arg);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && event.target.classList?.contains("row") && event.target.dataset.id) { select(event.target.dataset.id); render(); }
});
document.addEventListener("change", (event) => {
  const el = event.target;
  if (el.dataset.note) {
    const done = notesDone();
    if (el.checked) done[el.dataset.note] = true; else delete done[el.dataset.note];
    localStorage.setItem("hub.notes", JSON.stringify(done));
    render();
  } else if (el.dataset.flag && selected) {
    const set = new Set(chosenFlags(selected));
    if (el.checked) set.add(el.dataset.flag); else set.delete(el.dataset.flag);
    flagChoice[selected] = [...set];
    render();
  } else if (["logs-sid", "logs-dev", "logs-level"].includes(el.id)) {
    logsView[el.id.slice(5)] = el.value;
    if (el.id === "logs-sid") Object.assign(logsView, { incident: null, detail: null });
    loadLogs(true);
  } else if (el.id === "run-select") {
    log.chosen = el.value; log.run = null; log.offset = 0;
    $("log").textContent = "";
    pollLog();
  }
});
document.addEventListener("submit", (event) => {
  if (event.target.id !== "input-form") return;
  event.preventDefault();
  const field = $("input-text");
  const text = field.value;
  field.value = "";
  act(() => api(`/api/process/${selected}/input`, { text }));
});
$("stop-all").addEventListener("click", () => act(stopAll));
$("reload-btn").addEventListener("click", async () => {
  try { await api("/api/reload", {}); toast("설정을 다시 읽었습니다"); } catch (error) { toast("설정 오류: 이전 설정을 유지합니다\n" + error.message, true); }
  tick();
});

const routeFromHash = () => { const [name, arg] = location.hash.slice(1).split("/"); setPage(name || "home", arg); };
window.addEventListener("hashchange", routeFromHash);
tick().then(routeFromHash);
setInterval(tick, 1000);
setInterval(pollLog, 1000);
