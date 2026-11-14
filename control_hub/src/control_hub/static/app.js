// Control Hub page. Everything shown comes from /api/describe (the config) and /api/state
// (polled once a second). The page only ever sends ids back.
"use strict";

const $ = (id) => document.getElementById(id);
const LABEL = { off: "꺼짐", starting: "켜는 중", ready: "준비됨", stopping: "끄는 중", done: "끝남", failed: "오류" };
const ALIVE = ["starting", "ready", "stopping"];
const ERROR_LINE = /\b(error|fatal|traceback|exception|failed|failure|no such file|not found|refused|denied|timed out|unreachable|cannot|abort(ed)?|segmentation fault|killed)\b/i;

let D = null;            // describe
let S = null;            // state
let page = "run";
let profileId = localStorage.getItem("hub.profile");
let selected = null;     // process id shown in the detail panel
const flagChoice = {};   // pid -> [flag ids] chosen on this page
const log = { pid: null, run: null, offset: 0, chosen: "", runsFor: null, busy: false };

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

// ---------- rendering: chains and checks ----------
function evalNode(id) {
  if (D.checks[id]) {
    const r = S.checks[id] || { ok: null, detail: "" };
    return { id, type: "check", title: D.checks[id].title, status: r.ok === true ? "ok" : r.ok === null ? "wait" : "bad",
             detail: r.ok === null ? "확인 중" : r.detail, fix: D.checks[id].help };
  }
  const st = stateOf(id);
  const status = ["ready", "done"].includes(st.state) ? "ok" : st.state === "starting" ? "wait" : "bad";
  const issue = st.issues && st.issues.length ? st.issues[st.issues.length - 1] : null;
  let fix = "";
  if (st.state === "failed") fix = issue ? (issue.hint || issue.line) : "로그를 봅니다";
  else if (st.state === "off") fix = st.blockers && st.blockers.length ? st.blockers.join(" / ") : "꺼져 있습니다. 실행 페이지에서 켭니다";
  return { id, type: "proc", title: titleOf(id), status, detail: LABEL[st.state] + (st.state === "failed" ? ` (코드 ${st.exit_code ?? "?"})` : ""), fix };
}
function evalChain(chain) {
  const nodes = chain.items.map(evalNode);
  return { nodes, broken: nodes.findIndex((n) => n.status !== "ok") };
}
function renderSide() {
  setHTML($("side-chains"), D.chains.map((chain) => {
    const { nodes, broken } = evalChain(chain);
    if (broken < 0) return `<div class="chain-line" data-action="page" data-id="links"><span class="dot ok"></span><b>${esc(chain.title)}</b><small>전부 정상</small></div>`;
    const node = nodes[broken];
    return `<div class="chain-line ${node.status === "bad" ? "bad" : ""}" data-action="page" data-id="links"><span class="dot ${node.status}"></span><b>${esc(chain.title)}</b>
      <small>${esc(node.title)}: ${esc(node.detail)}</small></div>`;
  }).join(""));
  const failed = Object.keys(S.processes).filter((pid) => stateOf(pid).state === "failed");
  const nav = document.querySelector('#nav a[data-page="all"]');
  setHTML(nav, `전체${failed.length ? `<span class="count">${failed.length}</span>` : ""}`);
  const banner = $("failed-banner");
  banner.hidden = !failed.length;
  setHTML(banner, failed.length ? "오류로 끝난 프로세스: " + failed.map((pid) =>
    `<a href="#" data-action="select" data-id="${pid}">${esc(titleOf(pid))}</a>`).join(", ") + " (눌러서 로그 보기)" : "");
  document.title = failed.length ? `(${failed.length}) Control Hub` : "Control Hub";
  const error = $("config-error");
  error.hidden = !S.config_error;
  error.textContent = S.config_error ? `설정 파일 오류 (이전 설정으로 동작 중)\n${S.config_error}` : "";
}
function renderLinks() {
  setHTML($("chains"), D.chains.map((chain) => {
    const { nodes, broken } = evalChain(chain);
    const html = nodes.map((node, i) => {
      const cls = broken < 0 || i < broken ? "ok" : i === broken ? "broken" : "after";
      const action = node.type === "proc" ? `data-action="select" data-id="${node.id}"` : "";
      return `${i ? '<span class="arrow">→</span>' : ""}<div class="node ${cls} ${node.type}" ${action}>
        <div class="name"><span class="dot ${i === broken ? node.status : cls === "ok" ? "ok" : ""}"></span>${esc(node.title)}</div>
        <small>${esc(i === broken && node.status === "bad" ? "여기서 끊김 · " + node.detail : node.detail)}</small></div>`;
    }).join("");
    const fix = broken >= 0 && nodes[broken].fix
      ? `<div class="notice ${nodes[broken].status === "bad" ? "bad" : "warn"} fix"><b>${esc(nodes[broken].title)}</b>: ${esc(nodes[broken].fix)}</div>` : "";
    return `<div class="panel chain"><div class="panel-head"><h2>${esc(chain.title)}</h2>
      <span class="tag ${broken < 0 ? "ok" : "bad"}">${broken < 0 ? "전부 정상" : "끊김"}</span></div>
      <div class="chain-nodes">${html}</div>${fix}</div>`;
  }).join("") || '<p class="muted">설정에 사슬(chains)이 없습니다.</p>');
  setHTML($("checks-table"), `<tr><th>상태</th><th>점검</th><th>결과</th><th>대상</th></tr>` + Object.values(D.checks).map((check) => {
    const r = S.checks[check.id] || { ok: null, detail: "" };
    const tag = r.ok === true ? '<span class="tag ok">정상</span>' : r.ok === null ? '<span class="tag">확인 중</span>' : '<span class="tag bad">실패</span>';
    const link = check.link && r.ok ? ` <a href="${esc(check.target)}" target="_blank" rel="noopener">${esc(check.link)}</a>` : "";
    const fix = r.ok === false && check.help ? `<div class="fixline">${esc(check.help)}</div>` : "";
    return `<tr><td>${tag}</td><td><b>${esc(check.title)}</b>${fix}</td><td>${esc(r.detail)}${link}</td><td class="mono muted">${esc(check.kind)}: ${esc(check.target)}</td></tr>`;
  }).join(""));
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
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("on", a.dataset.page === page));
  $("page-run").hidden = page !== "run";
  $("page-all").hidden = page !== "all";
  $("work").hidden = page === "links";
  $("page-links").hidden = page !== "links";
  renderSide();
  if (page === "run") renderRun();
  if (page === "all") renderAll();
  if (page === "links") renderLinks(); else renderDetail();
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
function setPage(next) {
  page = ["run", "all", "links"].includes(next) ? next : "run";
  if (location.hash !== "#" + page) history.replaceState(null, "", "#" + page);
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
  else if (action === "page") setPage(id);
  else if (action === "select") {
    if (event.target.closest("button")) return;
    if (page === "links") setPage(D.processes[id] && D.profiles.some((p) => p.id === profileId && p.steps.some((s) => s.process === id)) ? "run" : "all");
    select(id);
    render();
  }
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
document.querySelectorAll("#nav a").forEach((a) => a.addEventListener("click", (event) => { event.preventDefault(); setPage(a.dataset.page); }));
$("stop-all").addEventListener("click", () => act(stopAll));
$("reload-btn").addEventListener("click", async () => {
  try { await api("/api/reload", {}); toast("설정을 다시 읽었습니다"); } catch (error) { toast("설정 오류: 이전 설정을 유지합니다\n" + error.message, true); }
  tick();
});

page = location.hash.slice(1) || "run";
tick().then(() => { setPage(page); });
setInterval(tick, 1000);
setInterval(pollLog, 1000);
