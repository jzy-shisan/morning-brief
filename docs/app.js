const GROUPS = {
  news:    { name: "新闻简报", desc: "前沿 · 世界 · 财经 · 体育" },
  student: { name: "学生简报", desc: "肥鱼主推 · 碎碎念 · 解忧铺 · 小试鱼刀" },
};
const app = document.getElementById("app");
const esc = (s = "") => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : "");
const cacheKey = (g) => `fyb-last-${g}`;

function splash() {
  app.innerHTML = `
  <div class="splash">
    <div class="logo">肥鱼简报</div>
    <h1>十分钟，过一遍今天</h1>
    <div class="choices">
      ${Object.entries(GROUPS).map(([k, v]) => `
        <button class="choice" data-go="${k}">
          <span class="txt"><strong>${v.name}</strong><span>${v.desc}</span></span>
          <span class="go">→</span>
        </button>`).join("")}
    </div>
  </div>`;
}

function card(it, idx) {
  const url = safeUrl(it.link);
  const title = esc(it.title);
  const heading = url
    ? `<a href="${esc(url)}" target="_blank" rel="noopener">${title}</a>`
    : title;
  const orig = it.orig ? `<div class="orig">${esc(it.orig)}</div>` : "";
  const points = (it.points || []).length
    ? `<ul>${it.points.map(p => `<li>${esc(p)}</li>`).join("")}</ul>` : "";
  const qa = it.question ? `
    <div class="qbox"><b>题目</b>${esc(it.question)}</div>
    <button class="btn-answer" type="button" aria-expanded="false" aria-controls="ans-${idx}">看解析</button>
    <div class="answer" id="ans-${idx}">${it.solution ? `${esc(it.solution)}\n\n` : ""}${esc(it.answer || "")}${it.point ? `\n\n考点：${esc(it.point)}` : ""}</div>` : "";
  const comment = it.comment ? `<div class="comment"><b>🐟 大肥鱼</b>${esc(it.comment)}</div>` : "";
  const tip = it.tip ? `<div class="tip">本鱼的建议：${esc(it.tip)}</div>` : "";
  const meta = it.badge ? `<div class="meta"><span>${esc(it.badge)}</span></div>` : "";
  const src = (it.source || url)
    ? `<p class="src">${it.source ? esc(it.source) : ""}${it.source && url ? '<span class="sp">·</span>' : ""}${url ? `<a href="${esc(url)}" target="_blank" rel="noopener">原文 ↗</a>` : ""}</p>`
    : "";
  return `<article class="card ${it.small ? "small" : ""}">
    <h4>${heading}</h4>
    ${orig}${meta}
    ${it.summary ? `<p class="summary">${esc(it.summary)}</p>` : ""}
    ${points}${qa}${comment}${tip}${src}
  </article>`;
}

// 同一板块里既有主条又有小条时，中间插一条分隔标签
function itemsHtml(items) {
  const mixed = items.some(i => i.small) && items.some(i => !i.small);
  let html = "";
  let marked = false;
  let idx = 0;
  for (const it of items) {
    if (mixed && it.small && !marked) {
      html += `<div class="divider"><span>还可以看看</span></div>`;
      marked = true;
    }
    html += card(it, idx++);
  }
  return html;
}

const PAST = `<p class="past"><a href="archive.html">查看往期晨报 →</a></p>`;

function render(data, group, notice) {
  const g = GROUPS[group];
  const dateEl = document.getElementById("date");
  if (dateEl) dateEl.textContent = (data.date || "").replace(/-/g, "·");
  document.getElementById("body").innerHTML = `
    ${notice ? `<p class="notice">${esc(notice)}</p>` : ""}
    <div class="intro"><h1>${esc(data.title || g.name)}</h1></div>
    ${(data.sections || []).map(s => `<section class="sec"><h3>${esc(s.name)}</h3>
      ${itemsHtml(s.items || [])}</section>`).join("")}
    ${PAST}`;
}

function renderState(kind) {
  const msg = {
    offline: ["🫧", "网络断了，本鱼这儿也没有存下来的", "最近一期还没成功打开过，等有网了再来。"],
    notfound: ["🫧", "这一期还没生成", "等一会儿再刷新，或者去翻翻往期。"],
    broken: ["🫧", "数据格式坏了", "生成脚本那边出了问题，去翻一下日志。"],
  }[kind] || ["🫧", "出了点小状况", "刷新一下试试。"];
  document.getElementById("body").innerHTML = `
    <div class="state" role="alert"><div class="big">${msg[0]}</div><h3>${msg[1]}</h3>
    <p>${msg[2]}</p>
    <p><a href="#/">← 回到选择页</a></p></div>
    ${PAST}`;
}

async function load(group) {
  const g = GROUPS[group];
  app.innerHTML = `
    <header class="top"><div class="inner">
      <div class="brand">🐟 大肥鱼</div>
      <nav class="tabs">${Object.entries(GROUPS).map(([k, v]) =>
        `<button class="${k === group ? "on" : ""}" data-go="${k}">${v.name}</button>`).join("")}</nav>
      <span class="date" id="date"></span>
    </div></header>
    <main class="wrap"><div id="body" role="status" aria-busy="true">
      <div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div>
    </div></main>
    <footer>本地生成 · GitHub Pages 托管 · 离线可看最近一期</footer>`;

  let data = null;
  let kind = null;
  try {
    const r = await fetch(`data/${group}.json`);
    if (!r.ok) throw new Error(`HTTP_${r.status}`);
    data = await r.json();
    try { localStorage.setItem(cacheKey(group), JSON.stringify(data)); } catch (e) {}
  } catch (err) {
    kind = /HTTP_4\d\d/.test(String(err.message)) ? "notfound"
         : err instanceof SyntaxError ? "broken" : "offline";
    try {
      const raw = localStorage.getItem(cacheKey(group));
      if (raw) data = JSON.parse(raw);
    } catch (e) {}
    if (!data) { renderState(kind); return; }
  }

  const body = document.getElementById("body");
  body.removeAttribute("aria-busy");
  if (!data.sections || !data.sections.length) { renderState("notfound"); return; }
  render(data, group, kind ? "离线 · 显示上次缓存的这一期" : "");
  body.removeAttribute("role");
}

function route() {
  const m = location.hash.match(/^#\/(news|student)$/);
  if (m) { load(m[1]); return; }
  if (location.hash && location.hash !== "#/" && location.hash !== "#") {
    history.replaceState(null, "", "#/");
  }
  splash();
}

document.addEventListener("click", (e) => {
  const goEl = e.target.closest("[data-go]");
  if (goEl) { location.hash = "#/" + goEl.dataset.go; return; }
  const btn = e.target.closest(".btn-answer");
  if (btn) {
    const box = document.getElementById(btn.getAttribute("aria-controls"));
    if (!box) return;
    const open = box.classList.toggle("show");
    btn.setAttribute("aria-expanded", open ? "true" : "false");
  }
});

window.addEventListener("hashchange", route);
route();
