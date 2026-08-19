# -*- coding: utf-8 -*-
"""Постын ээлжийг засах локал вэб интерфейс. Зөвхөн 127.0.0.1 дээр ажиллана."""

HTML = r"""<!DOCTYPE html>
<html lang="mn">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Threads ээлж засварлагч</title>
<style>
  :root{
    --bg:#0e0f13; --panel:#171922; --panel2:#1e212c; --line:#2a2e3c;
    --ink:#e8eaf0; --muted:#9aa1b4; --accent:#5b8cff; --ok:#3ecf8e;
    --warn:#f5a623; --bad:#ff5f56; --hold:#a78bfa;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
    font:15px/1.55 "Segoe UI",system-ui,-apple-system,sans-serif;}
  header{position:sticky;top:0;z-index:10;background:rgba(14,15,19,.94);
    backdrop-filter:blur(8px);border-bottom:1px solid var(--line);padding:14px 22px;
    display:flex;align-items:center;gap:16px;flex-wrap:wrap}
  h1{font-size:17px;margin:0;font-weight:600;letter-spacing:.2px}
  .stats{color:var(--muted);font-size:13px}
  .stats b{color:var(--ink);font-weight:600}
  .grow{flex:1}
  button{font:inherit;border:1px solid var(--line);background:var(--panel2);
    color:var(--ink);padding:8px 14px;border-radius:8px;cursor:pointer;transition:.15s}
  button:hover{border-color:var(--accent)}
  button.primary{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
  button.primary:hover{filter:brightness(1.1)}
  button.ghost{background:transparent}
  button.danger:hover{border-color:var(--bad);color:var(--bad)}
  main{max-width:940px;margin:0 auto;padding:22px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:12px;
    padding:16px;margin-bottom:14px}
  .card.posted{opacity:.5}
  .row{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
  label{font-size:12px;color:var(--muted);display:block;margin-bottom:4px}
  input,select,textarea{font:inherit;background:var(--panel2);color:var(--ink);
    border:1px solid var(--line);border-radius:8px;padding:9px 11px;width:100%}
  input:focus,select:focus,textarea:focus{outline:none;border-color:var(--accent)}
  textarea{resize:vertical;min-height:92px;line-height:1.6}
  .f-time{width:250px;flex:none}
  .f-status{width:170px;flex:none}
  .f-img{flex:1;min-width:220px}
  .t24{color:var(--accent);font-variant-numeric:tabular-nums;font-weight:600;margin-left:4px}
  .count{font-size:12px;font-variant-numeric:tabular-nums;white-space:nowrap;
    padding:3px 9px;border-radius:999px;border:1px solid var(--line)}
  .c-ok{color:var(--ok);border-color:rgba(62,207,142,.4)}
  .c-warn{color:var(--warn);border-color:rgba(245,166,35,.4)}
  .c-bad{color:var(--bad);border-color:rgba(255,95,86,.5)}
  .pill{font-size:11px;padding:3px 9px;border-radius:999px;border:1px solid var(--line);color:var(--muted)}
  .pill.hold{color:var(--hold);border-color:rgba(167,139,250,.4)}
  .pill.posted{color:var(--ok);border-color:rgba(62,207,142,.4)}
  .pill.failed{color:var(--bad);border-color:rgba(255,95,86,.5)}
  .bar{position:sticky;bottom:0;background:rgba(14,15,19,.94);backdrop-filter:blur(8px);
    border-top:1px solid var(--line);padding:14px 22px;display:flex;gap:12px;align-items:center}
  .msg{font-size:13px;color:var(--muted)}
  .msg.ok{color:var(--ok)} .msg.bad{color:var(--bad)}
  .hint{font-size:12px;color:var(--muted);margin-top:6px}
  .empty{text-align:center;color:var(--muted);padding:60px 0}
</style>
</head>
<body>
<header>
  <h1>Threads ээлж</h1>
  <div class="stats" id="stats"></div>
  <div class="grow"></div>
  <button class="ghost" onclick="addPost()">+ Пост нэмэх</button>
  <button class="ghost" onclick="load()">Сэргээх</button>
</header>

<main id="list"></main>

<div class="bar">
  <button class="primary" onclick="save()">Хадгалах</button>
  <span class="msg" id="msg">Өөрчлөлт хийгээд Хадгалах дарна.</span>
</div>

<script>
let queue = [];

const STATUSES = {
  pending: "Нийтлэгдэнэ",
  hold:    "Түр хүлээлгэсэн",
  posted:  "Нийтэлсэн",
  failed:  "Алдаатай",
  skipped: "Алгассан"
};

function countClass(n){ return n > 500 ? "c-bad" : n > 200 ? "c-warn" : "c-ok"; }
function esc(s){ return (s||"").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }

function render(){
  const list = document.getElementById("list");
  if(!queue.length){ list.innerHTML = '<div class="empty">Ээлж хоосон байна. "Пост нэмэх" дарна уу.</div>'; updateStats(); return; }

  queue.sort((a,b) => (a.scheduled_at||"").localeCompare(b.scheduled_at||""));

  list.innerHTML = queue.map((p,i) => {
    const n = (p.text||"").length;
    const done = p.status === "posted";
    return `
    <div class="card ${done?"posted":""}">
      <div class="row">
        <div class="f-time">
          <label>Огноо, цаг <span class="t24" id="t24_${i}">${esc(p.scheduled_at||"")}</span></label>
          <input type="datetime-local" value="${(p.scheduled_at||"").replace(" ","T")}"
                 onchange="upd(${i},'scheduled_at',this.value.replace('T',' '))" ${done?"disabled":""}>
        </div>
        <div class="f-status">
          <label>Төлөв</label>
          <select onchange="upd(${i},'status',this.value)" ${done?"disabled":""}>
            ${Object.entries(STATUSES).map(([k,v]) =>
              `<option value="${k}" ${p.status===k?"selected":""}>${v}</option>`).join("")}
          </select>
        </div>
        <div class="f-img">
          <label>Зургийн холбоос (сонголт, нээлттэй https)</label>
          <input type="url" placeholder="https://..." value="${esc(p.image_url||"")}"
                 oninput="upd(${i},'image_url',this.value||null)" ${done?"disabled":""}>
        </div>
      </div>

      <label>Бичвэр</label>
      <textarea oninput="upd(${i},'text',this.value)" ${done?"disabled":""}>${esc(p.text||"")}</textarea>

      <div class="row" style="margin-top:10px;margin-bottom:0">
        <span class="count ${countClass(n)}" id="cnt${i}">${n} тэмдэгт</span>
        ${p.status!=="pending" ? `<span class="pill ${p.status}">${STATUSES[p.status]||p.status}</span>` : ""}
        ${p.threads_id ? `<span class="pill posted">ID ${esc(p.threads_id)}</span>` : ""}
        ${p.error ? `<span class="pill failed">${esc(p.error)}</span>` : ""}
        <div class="grow"></div>
        ${done ? "" : `<button class="ghost danger" onclick="del(${i})">Устгах</button>`}
      </div>
      ${n>500 ? '<div class="hint" style="color:var(--bad)">500 тэмдэгтээс урт. Энэ пост нийтлэгдэхгүй.</div>'
        : n>200 ? '<div class="hint">200 тэмдэгтээс урт. Оролцоо буурах магадлалтай.</div>' : ""}
    </div>`;
  }).join("");
  updateStats();
}

function updateStats(){
  const c = s => queue.filter(p => p.status === s).length;
  document.getElementById("stats").innerHTML =
    `нийт <b>${queue.length}</b> · хүлээгдэж буй <b>${c("pending")}</b> · түр хүлээлгэсэн <b>${c("hold")}</b> · нийтэлсэн <b>${c("posted")}</b>`;
}

function upd(i,k,v){
  queue[i][k] = v;
  if(k === "scheduled_at"){
    const el = document.getElementById("t24_"+i);
    if(el) el.textContent = v;
  }
  if(k === "text"){
    const n = v.length, el = document.getElementById("cnt"+i);
    el.textContent = n + " тэмдэгт";
    el.className = "count " + countClass(n);
  }
  flag("Хадгалаагүй өөрчлөлт байна.","");
}

function del(i){
  if(!confirm("Энэ постыг устгах уу?")) return;
  queue.splice(i,1); render(); flag("Устгалаа. Хадгалахаа мартуузай.","");
}

function addPost(){
  const d = new Date(Date.now() + 864e5);
  const pad = x => String(x).padStart(2,"0");
  const at = `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} 08:30`;
  const id = Math.max(0, ...queue.map(p => p.id||0)) + 1;
  queue.push({id, scheduled_at: at, text: "", image_url: null, status: "pending"});
  render();
  window.scrollTo(0, document.body.scrollHeight);
}

function flag(t, cls){ const m = document.getElementById("msg"); m.textContent = t; m.className = "msg " + cls; }

async function load(){
  const r = await fetch("/api/queue");
  queue = await r.json();
  render();
  flag("Ачааллаа.","ok");
}

async function save(){
  const bad = queue.filter(p => (p.text||"").length > 500 && p.status === "pending");
  if(bad.length && !confirm(bad.length + " пост 500 тэмдэгтээс урт байна. Тэдгээр нийтлэгдэхгүй. Үргэлжлүүлэх үү?")) return;
  const r = await fetch("/api/queue", {
    method:"POST", headers:{"Content-Type":"application/json;charset=utf-8"},
    body: JSON.stringify(queue)
  });
  if(r.ok){ flag("Хадгалагдлаа.","ok"); load(); }
  else { flag("Алдаа: " + await r.text(),"bad"); }
}

load();
</script>
</body>
</html>
"""
