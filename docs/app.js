const GROUPS = {
  news:    { name: "新闻简报", desc: "前沿 · 世界 · 财经 · 体育" },
  student: { name: "学生简报", desc: "肥鱼主推 · 碎碎念 · 解忧铺 · 小试鱼刀" },
};
const DOMS = {
  "科技 AI": "tech", "商业财经": "biz", "社会热点": "society",
  "生活健康": "life", "数码娱乐": "digital",
};
const app = document.getElementById("app");
const esc = (s = "") => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : "");
const cacheKey = (g) => `fyb-last-${g}`;
const PAST = `<p class="past"><a href="archive.html">查看往期晨报 →</a></p>`;
const BOOT_KEY = "fyb-boot";
const BOOT_MS = 3000;

function digestHtml(d) {
  if (!d || !d.length) return "";
  return `<div class="digest"><span class="lb">今天三句话</span>
    <ol>${d.map(x => `<li>${esc(x)}</li>`).join("")}</ol></div>`;
}

function boot() {
  // 开头这张封面图停留 3 秒，点一下或按任意键也能直接进去
  app.innerHTML = `<div class="boot" id="boot"><img src="og.png" alt="肥鱼晨报"></div>`;
  document.documentElement.style.background = "#d1eaf9";
  const node = document.getElementById("boot");
  let done = false;
  const finish = () => {
    if (done) return;
    done = true;
    try { sessionStorage.setItem(BOOT_KEY, "1"); } catch (e) {}
    document.documentElement.style.background = "";
    if (node) node.classList.add("out");
    setTimeout(() => splash(), 260);
  };
  setTimeout(finish, BOOT_MS);
  node && node.addEventListener("click", finish, { once: true });
  document.addEventListener("keydown", finish, { once: true });
}

function splash() {
  app.innerHTML = `
  <div class="splash">
    <div class="logo">肥鱼晨报</div>
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

function panelHtml() {
  const sw = [["paper", "#f6f4ef", "#a8452a"], ["ink", "#f2f4f6", "#2f5d8a"],
              ["moss", "#f3f4ee", "#4d6141"], ["night", "#15161a", "#d98b5f"]]
    .map(([p, bg, ac]) => `<button class="swatch" type="button" data-p="${p}"
        style="background:${bg};border-color:rgba(0,0,0,.12)" aria-label="配色 ${p}"><i style="background:${ac}"></i></button>`)
    .join("");
  return `<div class="panel" id="panel">
    <div class="row"><span>配色</span><div>${sw}</div></div>
    <div class="row"><span>背景</span><div class="bgwrap">
      <input type="color" id="bgpick" value="#f6f4ef" aria-label="自定义背景色">
      <button type="button" id="bgreset">恢复默认</button></div></div>
    <div class="row"><span>字号</span><div class="sizewrap">
      <button type="button" data-fs="15px">小</button>
      <button type="button" data-fs="16px">中</button>
      <button type="button" data-fs="17.5px">大</button></div></div>
    <div class="row"><span>条数</span><div class="denwrap">
      <button type="button" data-den="1">少</button>
      <button type="button" data-den="2">标准</button>
      <button type="button" data-den="3">全</button></div></div>
  </div>`;
}

function card(it, idx, ord) {
  const url = safeUrl(it.link);
  const title = esc(it.title);
  const heading = url
    ? `<a href="${esc(url)}" target="_blank" rel="noopener">${title}</a>`
    : title;
  const orig = it.orig ? `<div class="orig">${esc(it.orig)}</div>` : "";
  const lead = it.summary ? `<p class="lead">${esc(it.summary)}</p>` : "";
  const points = (it.points || []).length
    ? `<ul class="points">${it.points.map(p => `<li>${esc(p)}</li>`).join("")}</ul>` : "";
  const qa = it.question ? `
    <div class="qbox"><b>题目</b>${esc(it.question)}</div>
    <button class="btn-answer" type="button" aria-expanded="false" aria-controls="ans-${idx}">看解析</button>
    <div class="answer" id="ans-${idx}">${it.solution ? `${esc(it.solution)}\n\n` : ""}${esc(it.answer || "")}${it.point ? `\n\n考点：${esc(it.point)}` : ""}</div>` : "";
  const comment = it.comment
    ? `<blockquote class="verdict"><span class="who">🐟 大肥鱼</span><span class="said">${esc(it.comment)}</span></blockquote>` : "";
  const tip = it.tip ? `<p class="tip">本鱼的建议：${esc(it.tip)}</p>` : "";
  const src = (it.source || url)
    ? `<p class="src">${it.source ? esc(it.source) : ""}${it.source && url ? '<span class="sp">·</span>' : ""}${url ? `<a href="${esc(url)}" target="_blank" rel="noopener">原文 ↗</a>` : ""}</p>`
    : "";
  return `<article class="${it.small ? "small" : ""}" data-ord="${ord}">
    <h3>${heading}</h3>
    ${orig}${lead}${points}${qa}${comment}${tip}${src}
  </article>`;
}

function sectionHtml(s, idx0) {
  const items = s.items || [];
  const dom = DOMS[s.name] || "";
  const plain = /^[^\u4e00-\u9fffA-Za-z0-9]/.test(s.name) ? " plain" : "";
  const body = items.map((it, i) => card(it, idx0 + i, i + 1)).join("");
  return `<section class="sec${plain}" data-dom="${dom}">
    <div class="sechead"><h2>${esc(s.name)}</h2>
      <span class="n">${String(items.length).padStart(2, "0")}</span><span class="fill"></span></div>
    ${body}
    ${items.length > 2 ? `<div class="more"><button type="button">还有 ${items.length - 2} 条 · 展开</button></div>` : ""}
  </section>`;
}

function shell(data, group, notice) {
  const g = GROUPS[group];
  const d = (data.date || "").split("-");
  const dateText = d.length === 3 ? `${d[0]} 年 ${+d[1]} 月 ${+d[2]} 日` : (data.date || "");
  const doms = (data.sections || []).map(s => [DOMS[s.name], s.name]).filter(p => p[0]);
  const tabs = doms.length > 1
    ? `<nav class="tabs"><button type="button" data-view="all" data-active="1">全部</button>${
        doms.map(([k, n]) => `<button type="button" data-view="${k}">${esc(n)}</button>`).join("")}</nav>`
    : "";
  return `<div id="progress"></div>
  <div class="wrap">
    <div class="topbar">
      <div class="brand"><a href="#/">🐟 肥鱼晨报</a></div>
      <div class="tools"><button type="button" id="tbtn" aria-expanded="false">外观</button></div>
    </div>
    ${panelHtml()}
    <header class="hd">
      <h1>${esc(data.title || g.name)}</h1>
      <div class="date">${dateText} · <span id="cnt">…</span> · 约 <span id="mins">…</span> 分钟</div>
      <div class="tagline">${esc(data.tagline || "十分钟，过一遍今天")}</div>
      <div class="rule"></div>
    </header>
    ${digestHtml(data.digest)}
    ${tabs}
    <main id="body">
      ${notice ? `<p class="notice">${esc(notice)}</p>` : ""}
      ${(data.sections || []).map((s) => sectionHtml(s, 0)).join("")}
    </main>
    ${PAST}
    <footer>本地生成 · GitHub Pages 托管 · 离线可看最近一期</footer>
  </div>`;
}

function loadingShell(group) {
  const other = group === "news" ? "student" : "news";
  return `<div class="wrap">
    <div class="topbar">
      <div class="brand"><a href="#/">🐟 肥鱼晨报</a></div>
      <div class="tools"><a href="#/${other}" style="border:0">${GROUPS[other].name}</a></div>
    </div>
    <div id="body" role="status" aria-busy="true">
      <div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div>
    </div>
  </div>`;
}

function renderState(kind) {
  const msg = {
    offline: ["🫧", "网络断了，本鱼这儿也没有存下来的", "最近一期还没成功打开过，等有网了再来。"],
    notfound: ["🫧", "这一期还没生成", "等一会儿再刷新，或者去翻翻往期。"],
    broken: ["🫧", "数据格式坏了", "生成脚本那边出了问题，去翻一下日志。"],
  }[kind] || ["🫧", "出了点小状况", "刷新一下试试。"];
  app.innerHTML = `<div class="wrap">
    <div class="state" role="alert"><div class="big">${msg[0]}</div><h1>${msg[1]}</h1>
    <p>${msg[2]}</p><p><a href="#/">← 回到选择页</a></p></div>
    ${PAST}</div>`;
}

async function load(group) {
  app.innerHTML = loadingShell(group);
  let data = null, kind = null;
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
  if (!data.sections || !data.sections.length) { renderState("notfound"); return; }
  app.innerHTML = shell(data, group, kind ? "离线 · 显示上次缓存的这一期" : "");
  if (window.FybTheme) window.FybTheme.init();
  window.scrollTo(0, 0);
  stateBanner();
}

function route() {
  const m = location.hash.match(/^#\/(news|student)$/);
  if (m) { load(m[1]); return; }
  if (location.hash && location.hash !== "#/" && location.hash !== "#") {
    history.replaceState(null, "", "#/");
  }
  let seen = "";
  try { seen = sessionStorage.getItem(BOOT_KEY) || ""; } catch (e) {}
  if (!seen && !/noboot/.test(location.search)) { boot(); return; }
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

async function stateBanner() {
  try {
    const r = await fetch("data/state.json", { cache: "no-store" });
    if (!r.ok) return;
    const st = await r.json();
    if (st.ok !== false) return;
    const el = document.querySelector("main#body");
    if (!el) return;
    const box = document.createElement("p");
    box.className = "banner";
    box.textContent = `⚠️ 今天的简报没生成成功（${st.at || ""}）：${st.error || "原因未知"}，先看昨天的。`;
    el.prepend(box);
  } catch (e) {}
}

window.addEventListener("hashchange", route);
route();
