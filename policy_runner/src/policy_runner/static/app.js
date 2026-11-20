const $ = (id) => document.getElementById(id);
const ms = (v) => (v === null || v === undefined ? "—" : `${Math.round(v)} ms`);

function cell(text, cls) {
  const td = document.createElement("td");
  td.textContent = text;
  if (cls) td.className = cls;
  return td;
}

function renderStreams(streams) {
  const body = $("streams");
  body.replaceChildren();
  for (const [name, s] of Object.entries(streams)) {
    const over = s.obs_age_ms !== null && s.obs_age_ms > s.max_age_ms;
    const row = document.createElement("tr");
    row.append(
      cell(name),
      cell(s.status, s.status === "ok" ? "ok" : s.status === "error" ? "bad" : "warn"),
      cell(s.hz.toFixed(1), "num"),
      cell(s.age_s === null ? "—" : ms(s.age_s * 1000), "num"),
      cell(`${ms(s.obs_age_ms)} / ${ms(s.max_age_ms)}`, over ? "num bad" : "num"),
    );
    body.append(row);
  }
}

function render(s) {
  $("offline").style.display = "none";
  $("state").textContent = s.state;
  $("state").className = `badge ${s.state}`;
  $("mode").textContent = s.mode === "hand" ? "손 UDP 로 보냄" : "dry-run (보내지 않음)";
  $("endpoint").textContent = s.endpoint;
  $("checkpoint").textContent = s.checkpoint;
  $("server_checkpoint").textContent = s.server_checkpoint ?? "—";
  $("prompt").textContent = s.prompt || "—";
  $("connected").textContent = s.infer.connected ? "연결됨" : "끊김";
  $("connected").className = s.infer.connected ? "ok" : "bad";
  $("rtt").textContent = ms(s.infer.rtt_ms);
  $("infer").textContent = ms(s.infer.infer_ms);
  const c = s.chunk;
  $("chunk").textContent = c.id ? `#${c.id}  행 ${c.row} / ${c.of}${c.active ? "" : " (끝남)"}` : "—";
  $("chunk_age").textContent = ms(c.age_ms);
  $("sent").textContent = String(s.sent.sent);
  renderStreams(s.streams);
  const list = $("problems");
  list.replaceChildren(...(s.problems.length ? s.problems : ["없음"]).map((p) => {
    const li = document.createElement("li");
    li.textContent = p;
    return li;
  }));
  $("trace").textContent = `trace: ${s.trace}`;
  $("arm").disabled = s.state !== "READY";
  $("disarm").disabled = !(s.state === "RUNNING" || s.state === "HOLD");
  $("reset").disabled = s.state !== "FAULT";
}

async function refresh() {
  try {
    const reply = await fetch("api/state");
    render(await reply.json());
  } catch {
    $("offline").style.display = "inline";
  }
}

async function post(path) {
  const reply = await fetch(path, { method: "POST" });
  render(await reply.json());
}

$("arm").onclick = () => post("api/arm");
$("disarm").onclick = () => post("api/disarm");
$("reset").onclick = () => post("api/reset");
refresh();
setInterval(refresh, 500);
