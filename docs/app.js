const GROUPS = {
  news:    { name: "新闻简报", desc: "前沿 · 世界 · 财经 · 体育" },
  student: { name: "学生简报", desc: "肥鱼主推 · 碎碎念 · 解忧铺 · 小试鱼刀" },
};
const app = document.getElementById("app");
const esc = (s = "") => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function go(g) { location.hash = "#/" + g; }

function splash() {
  app.innerHTML = `
  <div class="splash">
    <div class="logo">肥鱼简报</div>
    <h1>十分钟，过一遍今天</h1>
    <div class="choices">
      ${Object.entries(GROUPS).map(([k, v]) => `
        <button class="choice" onclick="go('${k}')">
          <span class="txt"><strong>${v.name}</strong><span>${v.desc}</span></span>
          <span class="go">→</span>
        </button>`).join("")}
    </div>
  </div>`;
}

function card(it) {
  const title = esc(it.title);
  const orig = it.orig ? `<div class="orig">${esc(it.orig)}</div>` : "";
  const points = (it.points || []).length
    ? `<ul>${it.points.map(p => `<li>${esc(p)}</li>`).join("")}</ul>` : "";
  const qa = it.question ? `
    <div class="qbox"><b>题目</b>${esc(it.question)}</div>
    <button class="btn-answer" onclick="this.nextElementSibling.classList.toggle('show')">看解析</button>
    <div class="answer">${it.solution ? `${esc(it.solution)}\n\n` : ""}${esc(it.answer || "")}${it.point ? `\n\n考点：${esc(it.point)}` : ""}</div>` : "";
  const comment = it.comment ? `<div class="comment"><b>🐟 大肥鱼</b>${esc(it.comment)}</div>` : "";
  const tip = it.tip ? `<div class="tip">本鱼的建议：${esc(it.tip)}</div>` : "";
  const meta = it.badge ? `<div class="meta"><span>${esc(it.badge)}</span></div>` : "";
  const src = (it.source || it.link)
    ? `<p class="src">${it.source ? esc(it.source) : ""}${it.source && it.link ? '<span class="sp">·</span>' : ""}${it.link ? `<a href="${esc(it.link)}" target="_blank" rel="noopener">原文 ↗</a>` : ""}</p>`
    : "";
  return `<article class="card ${it.small ? "small" : ""}">
    <h4>${title}</h4>
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
  for (const it of items) {
    if (mixed && it.small && !marked) {
      html += `<div class="divider"><span>还可以看看</span></div>`;
      marked = true;
    }
    html += card(it);
  }
  return html;
}

async function load(group) {
  const g = GROUPS[group];
  app.innerHTML = `
    <header class="top"><div class="wrap inner">
      <div class="brand">🐟 大肥鱼</div>
      <nav class="tabs">${Object.entries(GROUPS).map(([k, v]) =>
        `<button class="${k === group ? "on" : ""}" onclick="go('${k}')">${v.name}</button>`).join("")}</nav>
      <span class="date" id="date"></span>
    </div></header>
    <main class="wrap"><div id="body"><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div></div></main>
    <footer>本地生成 · GitHub Pages 托管 · 不联网也能看历史</footer>`;
  try {
    const r = await fetch(`data/${group}.json?t=${Date.now()}`, { cache: "no-cache" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    const data = await r.json();
    document.getElementById("date").textContent = data.date || "";
    const body = document.getElementById("body");
    if (!data.sections || !data.sections.length) throw new Error("empty");
    body.innerHTML = `
      <div class="intro"><h2>${esc(data.title || g.name)}</h2></div>
      ${data.sections.map(s => `<section class="sec"><h3>${esc(s.name)}</h3>
        ${itemsHtml(s.items || [])}</section>`).join("")}
      <p class="past"><a href="archive.html">查看往期晨报 →</a></p>`;
  } catch (e) {
    document.getElementById("body").innerHTML = `
      <div class="state"><div class="big">🫧</div><h3>今天的内容还没生成</h3>
      <p>先在本机跑一次生成脚本，再刷新这一页。</p>
      <p><a href="#/">← 回到选择页</a></p></div>`;
  }
}

function route() {
  const m = location.hash.match(/^#\/(news|student)$/);
  if (m) load(m[1]); else splash();
}
window.go = go;
window.addEventListener("hashchange", route);
route();
