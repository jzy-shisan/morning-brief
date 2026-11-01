#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""肥鱼晨报 · 分享版 HTML 渲染器

把 morning_brief.py 产出的 Markdown 简报渲染成一份自包含的 HTML：

  * 极简精修排版：暖纸底 + 发丝线 + 衬线标题，单列窄栏，为"十分钟读完"设计
  * 模块自定义：share_config.json 里逐板块开关、排序、每板块条数上限
  * 关键词优先：命中关键词的条目在本板块内置顶并标记，正文淡底强调
  * 少量外观自定义：3 套配色预设 + 字号档位，选择存 localStorage

用法:
    python render_html.py                      # 渲染 早晨简报.md
    python render_html.py --md history/2026-10-29.md
    python render_html.py --all                # 渲染 history/ 下全部，并生成 index.html

不依赖任何第三方库。
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "share_config.json"
HIST_DIR = BASE_DIR / "history"
SHARE_DIR = BASE_DIR / "share"
OUT_HTML = BASE_DIR / "早晨简报.html"

DEFAULT_CONFIG = {
    "site_title": "肥鱼晨报",
    "tagline": "十分钟，过一遍今天",
    "sections": [
        {"id": "tech",    "enabled": True, "limit": 2},
        {"id": "biz",     "enabled": True, "limit": 2},
        {"id": "society", "enabled": True, "limit": 2},
        {"id": "life",    "enabled": True, "limit": 2},
        {"id": "digital", "enabled": True, "limit": 2},
    ],
    "keywords": ["DeepSeek", "芯片", "半导体", "Minecraft", "模组", "开源", "CRISPR", "量子", "机器人"],
    "show_tips": False,
    "show_points": True,
    "summary_sentences": 0,
    "items_per_section": 2,
    "theme": "paper",
}

# 领域顺序 & 展示名（「全部」是前端聚合视图，不落盘）
DOMAINS = [
    ("tech", "科技 AI"),
    ("biz", "商业财经"),
    ("society", "社会热点"),
    ("life", "生活健康"),
    ("digital", "数码娱乐"),
]

SECTION_IDS = {
    "科技AI": "tech",
    "科技 AI": "tech",
    "科技ai": "tech",
    "商业财经": "biz",
    "社会热点": "society",
    "生活健康": "life",
    "数码娱乐": "digital",
    # 旧版板块名，兼容历史 HTML/Markdown
    "生物前沿": "life",
    "AI 前沿": "tech",
    "AI前沿": "tech",
    "我的世界": "digital",
    "中国教育": "society",
    "财经快报": "biz",
    "体育·电竞": "digital",
    "心理与认知": "life",
}

EMOJI_RE = re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]+\s*")


# --------------------------------------------------------------------------- #
# 解析 Markdown
# --------------------------------------------------------------------------- #
def parse_markdown(text: str) -> dict:
    lines = text.replace("\r\n", "\n").split("\n")
    doc = {"date": "", "weekday": "", "meta": "", "sections": [], "tips": [], "footer": ""}
    cur_section = None
    cur_item = None
    in_points = False
    in_tips = False

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        # 页脚先于一切分支处理（它在小公告栏之后，否则会被 tips 分支吃掉）
        if stripped.startswith("*生成于"):
            doc["footer"] = stripped.strip("*").strip()
            continue

        # 一级标题：日期
        m = re.match(r"^#\s+(.*)$", stripped)
        if m:
            head = m.group(1)
            in_tips = False
            dm = re.search(r"(\d{4})-(\d{2})-(\d{2})", head)
            if dm:
                doc["date"] = dm.group(0)
                try:
                    d = dt.date(int(dm.group(1)), int(dm.group(2)), int(dm.group(3)))
                    doc["weekday"] = "一二三四五六日"[d.weekday()]
                except ValueError:
                    doc["weekday"] = ""
            continue

        # 二级标题：板块
        m = re.match(r"^##\s+(.*)$", stripped)
        if m:
            name = EMOJI_RE.sub("", m.group(1)).strip()
            if "公告栏" in name:
                in_tips = True
                cur_section = None
                cur_item = None
                continue
            in_tips = False
            cur_section = {
                "id": SECTION_IDS.get(name, name),
                "name": name,
                "items": [],
                "empty_note": "",
            }
            doc["sections"].append(cur_section)
            cur_item = None
            continue

        # 三级标题：条目
        m = re.match(r"^###\s+(?:\d+\.\s*)?(.*)$", stripped)
        if m and cur_section is not None and not in_tips:
            cur_item = {
                "title": m.group(1).strip(),
                "summary": "",
                "points": [],
                "comment": "",
                "source": "",
                "link": "",
            }
            cur_section["items"].append(cur_item)
            in_points = False
            continue

        if in_tips:
            if stripped.startswith("> **") and "·" in stripped:
                mm = re.match(r"^>\s+\*\*(.+?)\*\*\s*·\s*(.*)$", stripped)
                if mm:
                    doc["tips"].append(
                        {"category": mm.group(1).strip(), "tip": mm.group(2).strip(), "comment": ""}
                    )
            elif stripped.startswith("> 🐋") or stripped.startswith(">🐋"):
                if doc["tips"]:
                    doc["tips"][-1]["comment"] = re.sub(r"^>\s*🐋\s*", "", stripped).strip()
            continue

        if stripped.startswith("*生成于"):
            doc["footer"] = stripped.strip("*").strip()
            continue

        if cur_item is None:
            if stripped.startswith("> 大肥鱼出品") or stripped.startswith("> 🐋 出品"):
                doc["meta"] = stripped.lstrip("> ").strip()
            elif stripped.startswith("*生成于"):
                doc["footer"] = stripped.strip("*").strip()
            continue

        if stripped.startswith("**核心观点**") or stripped.startswith("**摘要**"):
            cur_item["summary"] = re.sub(r"^\*\*(?:核心观点|摘要)\*\*[：:]\s*", "", stripped).strip()
            in_points = False
        elif stripped.startswith("**内容摘要**") or stripped.startswith("**核心要点**"):
            in_points = True
        elif stripped.startswith("- ") and in_points:
            cur_item["points"].append(stripped[2:].strip())
        elif re.match(r"^>\s*(?:🐋\s*)?\*\*(?:大肥鱼|有什么用)\*\*[：:]", stripped):
            body = re.sub(r"^>\s*(?:🐋\s*)?\*\*(?:大肥鱼|有什么用)\*\*[：:]\s*", "", stripped).strip()
            cur_item["comment"] = body
            in_points = False
        elif stripped.startswith("*来源"):
            body = stripped.strip("*")
            body = re.sub(r"^来源[：:]\s*", "", body)
            lm = re.search(r"\[原文\]\((.+?)\)", body)
            if lm:
                cur_item["link"] = lm.group(1).strip()
                body = body[: lm.start()]
            cur_item["source"] = body.strip(" ·").strip()
            in_points = False
        elif stripped and not cur_item["summary"] and cur_item["title"] == "":
            pass

    # 空板块提示
    for sec in doc["sections"]:
        if not sec["items"]:
            sec["empty_note"] = "今天这块没什么值得看的。"
    return doc


# --------------------------------------------------------------------------- #
# 关键词
# --------------------------------------------------------------------------- #
def find_keywords(text: str, keywords: list[str]) -> list[str]:
    hits = []
    low = text.lower()
    for kw in keywords:
        if kw and kw.lower() in low:
            hits.append(kw)
    return hits


def highlight(text: str, keywords: list[str]) -> str:
    """先按关键词切分，再逐段转义，避免破坏 HTML 结构。"""
    if not keywords:
        return html.escape(text)
    atoms = []
    for kw in sorted([k for k in keywords if k], key=len, reverse=True):
        esc = re.escape(kw)
        if kw.isascii():
            # 英文关键词按词边界匹配，避免把 smCRISPRa 拆成 sm / CRISPR / a
            atoms.append(rf"(?<![A-Za-z0-9]){esc}(?![A-Za-z0-9])")
        else:
            atoms.append(esc)
    if not atoms:
        return html.escape(text)
    pattern = "|".join(atoms)
    out = []
    pos = 0
    for m in re.finditer(pattern, text, flags=re.IGNORECASE):
        out.append(html.escape(text[pos:m.start()]))
        out.append(f'<em class="kw">{html.escape(m.group(0))}</em>')
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)


def reading_minutes(doc: dict, cfg: dict) -> int:
    keep = int(cfg.get("summary_sentences", 1))
    chars = 0
    for sec in enabled_sections(doc, cfg):
        for it in sec["items"][: sec["limit"]]:
            chars += (
                len(it["title"])
                + len(trim_summary(it["summary"], keep))
                + len(it["comment"])
            )
    return max(1, round(chars / 420))


def enabled_sections(doc: dict, cfg: dict) -> list[dict]:
    by_id = {s["id"]: s for s in doc["sections"]}
    order = [c for c in cfg.get("sections", []) if c.get("enabled", True)]
    out = []
    for conf in order:
        sec = by_id.get(conf["id"])
        if not sec or not sec["items"]:
            continue
        sec = dict(sec)
        sec["limit"] = int(conf.get("limit", cfg.get("items_per_section", 2)))
        sec["items"] = sort_items(sec["items"], cfg.get("keywords", []))
        out.append(sec)
    # 配置里没列到的板块，附在末尾，保持可见
    listed = {c["id"] for c in order}
    for sec in doc["sections"]:
        if sec["id"] in listed or not sec["items"]:
            continue
        sec = dict(sec)
        sec["limit"] = int(cfg.get("items_per_section", 2))
        sec["items"] = sort_items(sec["items"], cfg.get("keywords", []))
        out.append(sec)
    return out


def sort_items(items: list[dict], keywords: list[str]) -> list[dict]:
    scored = []
    for idx, it in enumerate(items):
        hits = find_keywords(it["title"] + " " + it["summary"], keywords)
        it = dict(it)
        it["hits"] = hits
        scored.append((0 if hits else 1, idx, it))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [x[2] for x in scored]


# --------------------------------------------------------------------------- #
# CSS / 主题
# --------------------------------------------------------------------------- #
PRESETS = {
    "paper": {
        "label": "纸",
        "bg": "#f6f4ef",
        "surface": "#fffefb",
        "fg": "#1c1a17",
        "muted": "#8a847a",
        "line": "rgba(28,26,23,.10)",
        "accent": "#a8452a",
    },
    "ink": {
        "label": "墨",
        "bg": "#f2f4f6",
        "surface": "#fbfcfd",
        "fg": "#16202a",
        "muted": "#7d8894",
        "line": "rgba(22,32,42,.10)",
        "accent": "#2f5d8a",
    },
    "moss": {
        "label": "苔",
        "bg": "#f3f4ee",
        "surface": "#fcfdf8",
        "fg": "#1d2118",
        "muted": "#828777",
        "line": "rgba(29,33,24,.10)",
        "accent": "#4d6141",
    },
    "night": {
        "label": "夜",
        "bg": "#15161a",
        "surface": "#1c1e23",
        "fg": "#e8e6e1",
        "muted": "#8b8a86",
        "line": "rgba(232,230,225,.12)",
        "accent": "#d98b5f",
    },
}

CSS = """
:root{
  --bg:__BG__; --surface:__SURFACE__; --fg:__FG__; --muted:__MUTED__;
  --line:__LINE__; --accent:__ACCENT__;
  --serif: "Noto Serif SC","Source Han Serif SC","Songti SC","SimSun",Georgia,serif;
  --sans: -apple-system,"Segoe UI","Microsoft YaHei UI","PingFang SC","Hiragino Sans GB",sans-serif;
  --fs: 16px;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:var(--bg); color:var(--fg);
  font-family:var(--sans); font-size:var(--fs); line-height:1.75;
  -webkit-font-smoothing:antialiased;
  transition:background .35s ease,color .35s ease;
}
#progress{position:fixed;top:0;left:0;height:2px;width:0;background:var(--accent);
  z-index:50;transition:width .1s linear;opacity:.85}
.wrap{max-width:728px;margin:0 auto;padding:72px 28px 96px}

/* 顶栏 */
.top{display:flex;align-items:center;justify-content:space-between;margin-bottom:44px}
.brand{font-family:var(--serif);font-size:15px;letter-spacing:.18em;color:var(--muted)}
.tools{display:flex;gap:6px}
.tools button{
  border:1px solid var(--line);background:transparent;color:var(--muted);
  font-family:var(--sans);font-size:12px;letter-spacing:.08em;
  padding:5px 10px;border-radius:999px;cursor:pointer;transition:.2s;
}
.tools button:hover{color:var(--fg);border-color:var(--muted)}
.panel{
  display:none;margin:0 0 40px;padding:16px 18px;border:1px solid var(--line);
  border-radius:14px;background:var(--surface);
}
.panel.open{display:block}
.panel .row{display:flex;align-items:center;gap:12px;margin:8px 0}
.panel .row > span{font-size:12px;color:var(--muted);letter-spacing:.1em;min-width:52px}
.swatch{width:26px;height:26px;border-radius:50%;border:1px solid var(--line);cursor:pointer;
  position:relative;transition:.2s;display:flex;align-items:center;justify-content:center;padding:0}
.swatch i{display:block;width:9px;height:9px;border-radius:50%}
.swatch:hover{transform:scale(1.08)}
.swatch[data-active="1"]{box-shadow:0 0 0 2px var(--bg),0 0 0 3px var(--accent)}
.sizewrap button{font-size:12px;padding:3px 9px;border-radius:999px;border:1px solid var(--line);
  background:transparent;color:var(--muted);cursor:pointer;margin-right:4px}
.sizewrap button[data-active="1"]{color:var(--accent);border-color:var(--accent)}
.bgwrap{display:flex;align-items:center;gap:10px}
.bgwrap input[type=color]{width:26px;height:26px;padding:0;border:1px solid var(--line);
  border-radius:50%;background:transparent;cursor:pointer;-webkit-appearance:none;appearance:none}
.bgwrap input[type=color]::-webkit-color-swatch-wrapper{padding:2px}
.bgwrap input[type=color]::-webkit-color-swatch{border:none;border-radius:50%}
.bgwrap button{font-size:12px;padding:3px 9px;border-radius:999px;border:1px solid var(--line);
  background:transparent;color:var(--muted);cursor:pointer}

/* 领域切换 */
.tabs{display:flex;flex-wrap:wrap;gap:6px;justify-content:center;margin:0 0 40px;
  position:sticky;top:0;z-index:30;padding:10px 0 12px;
  background:linear-gradient(var(--bg) 72%,transparent)}
.tabs::after{content:"";position:absolute;left:0;right:0;bottom:0;height:1px;
  background:var(--line);opacity:.5}
.tabs button{
  border:1px solid transparent;background:transparent;color:var(--muted);cursor:pointer;
  font-family:var(--sans);font-size:12.5px;letter-spacing:.1em;padding:5px 11px;border-radius:999px;
  transition:.2s;
}
.tabs button:hover{color:var(--fg)}
.tabs button[data-active="1"]{color:var(--accent);border-color:var(--line);background:var(--surface)}

/* 头图区 */
header{text-align:center;margin-bottom:44px;position:relative}
h1{font-family:var(--serif);font-weight:600;font-size:clamp(30px,5vw,42px);
  line-height:1.3;margin:0 0 14px;letter-spacing:.01em}
.date{font-size:13px;letter-spacing:.3em;color:var(--muted);text-transform:uppercase}
.tagline{margin-top:18px;font-family:var(--serif);font-size:15px;color:var(--muted);letter-spacing:.06em}
.rule{width:36px;height:1px;background:var(--accent);margin:26px auto 0;opacity:.7}

/* 板块 */
section{margin:0 0 52px}
.sechead{display:flex;align-items:baseline;gap:12px;margin-bottom:22px}
.sechead h2{font-family:var(--serif);font-size:17px;font-weight:600;margin:0;letter-spacing:.12em}
.sechead h2::before{content:"";display:inline-block;width:5px;height:5px;margin-right:11px;
  border:1px solid var(--accent);transform:rotate(45deg) translateY(-3px);opacity:.75}
.sechead .n{font-size:11px;color:var(--muted);letter-spacing:.2em}
.sechead .fill{flex:1;height:1px;background:var(--line);transform:translateY(-4px)}

/* 条目 */
article{padding:26px 0;border-top:1px solid var(--line)}
article:first-of-type{border-top:none;padding-top:0}
.hit{display:inline-flex;align-items:center;gap:5px;font-size:11px;letter-spacing:.16em;
  color:var(--accent);margin-bottom:9px}
.hit::before{content:"";width:5px;height:5px;border-radius:50%;background:var(--accent)}
.hit .pin{font-size:10px;letter-spacing:.06em;color:var(--muted);margin-left:4px}
h3{font-family:var(--serif);font-weight:600;font-size:21px;line-height:1.5;margin:0 0 12px;
  letter-spacing:.005em}
h3 a{color:inherit;text-decoration:none}
h3 a:hover{color:var(--accent)}
.orig{font-family:var(--sans);font-size:12.5px;line-height:1.65;color:var(--muted);
  letter-spacing:.01em;margin:-6px 0 12px}
.lead{margin:0 0 16px;color:var(--fg);opacity:.92;font-size:15.5px;line-height:1.9;
  letter-spacing:.005em}
.points{margin:0 0 4px;padding:0;list-style:none;font-size:14.5px;color:var(--fg);opacity:.78;
  line-height:1.85}
.points li{position:relative;padding-left:16px;margin:5px 0}
.points li::before{content:"";position:absolute;left:2px;top:.72em;width:4px;height:4px;
  border-radius:50%;background:var(--accent);opacity:.55}
em.kw{font-style:normal;background:__KW__;border-radius:3px;padding:0 3px;
  box-decoration-break:clone;-webkit-box-decoration-break:clone}
.verdict{margin:18px 0 0;padding:12px 0 12px 16px;border-left:2px solid var(--line);
  font-size:14.5px;color:var(--fg);opacity:.88;line-height:1.85}
.verdict .who{font-family:var(--serif);color:var(--accent);letter-spacing:.18em;margin-right:10px;
  font-size:12.5px;white-space:nowrap}
.verdict .said{display:inline}
details{margin-top:14px}
details summary{cursor:pointer;font-size:12.5px;color:var(--muted);letter-spacing:.12em;
  list-style:none;display:inline-flex;align-items:center;gap:6px;user-select:none}
details summary::-webkit-details-marker{display:none}
details summary::before{content:"＋";font-size:11px;transition:transform .2s;color:var(--accent)}
details[open] summary::before{content:"－"}
details ul{margin:12px 0 0;padding-left:18px;font-size:14.5px;color:var(--muted);line-height:1.9}
details ul li{margin:3px 0}
.src{margin-top:16px;font-size:12px;color:var(--muted);letter-spacing:.06em}
.src a{color:var(--muted);text-decoration:none;border-bottom:1px solid var(--line)}
.src a:hover{color:var(--accent);border-color:var(--accent)}
.more{margin-top:18px}
.more button{background:transparent;border:none;padding:0;color:var(--muted);font-size:12.5px;
  letter-spacing:.1em;cursor:pointer;border-bottom:1px dashed var(--line);font-family:var(--sans)}
.more button:hover{color:var(--accent);border-color:var(--accent)}
.hidden{display:none}
.hidden-sec{display:none}
.empty{font-size:13px;color:var(--muted);font-style:normal;padding:4px 0}

/* 小公告栏 */
.tips{border-top:1px solid var(--line);padding-top:34px;margin-top:8px}
.tips h2{font-family:var(--serif);font-size:15px;font-weight:600;letter-spacing:.16em;
  color:var(--muted);margin:0 0 20px}
.tip{padding:14px 0;border-top:1px dashed var(--line)}
.tip:first-of-type{border-top:none}
.tip .cat{font-size:11px;letter-spacing:.2em;color:var(--accent);margin-bottom:6px}
.tip .txt{font-size:15px}
.tip .cm{margin-top:9px;font-size:13.5px;color:var(--muted);line-height:1.8}

footer{margin-top:64px;padding-top:24px;border-top:1px solid var(--line);
  text-align:center;font-size:11.5px;color:var(--muted);letter-spacing:.1em;line-height:2}
footer::before{content:"◦ ◦ ◦";display:block;margin-bottom:14px;font-size:9px;
  letter-spacing:.5em;color:var(--accent);opacity:.5}

@media (max-width:640px){
  .wrap{padding:48px 20px 72px}
  h3{font-size:19px}
  .lead{font-size:15px}
  .tabs{gap:4px;margin-bottom:34px}
}
@media print{
  #progress,.tools,.panel,.more{display:none!important}
  body{background:#fff}
  article{break-inside:avoid}
}
"""

JS = """
(function(){
  var root=document.documentElement, KEY='fyb-share-theme';
  var sw=document.querySelectorAll('.swatch');
  var sz=document.querySelectorAll('.sizewrap button');
  var saved=null;
  try{saved=JSON.parse(localStorage.getItem(KEY)||'null')}catch(e){}
  function apply(cfg){
    if(!cfg) return;
    if(cfg.vars){for(var k in cfg.vars){root.style.setProperty(k,cfg.vars[k])}}
    if(cfg.fs){root.style.setProperty('--fs',cfg.fs)}
    sw.forEach(function(b){b.dataset.active = (b.dataset.p===cfg.p)?'1':'0'});
    sz.forEach(function(b){b.dataset.active = (b.dataset.fs===cfg.fs)?'1':'0'});
  }
  function save(cfg){try{localStorage.setItem(KEY,JSON.stringify(cfg))}catch(e){}}
  sw.forEach(function(b){
    b.addEventListener('click',function(){
      var vars=JSON.parse(b.dataset.vars);
      var cur={p:b.dataset.p,vars:vars,fs:(saved&&saved.fs)||''};
      Object.keys(vars).forEach(function(k){root.style.setProperty(k,vars[k])});
      apply(cur);save(cur);
    });
  });
  sz.forEach(function(b){
    b.addEventListener('click',function(){
      var fs=b.dataset.fs, vars=saved?saved.vars:null, p=saved?saved.p:'paper';
      var cur={p:p,vars:vars,fs:fs};
      apply(cur);save(cur);
    });
  });
  var t=document.getElementById('tbtn'), panel=document.getElementById('panel');
  // #night 这类链接可直接指定配色；#panel 展开外观面板
  (function(){
    var h=(location.hash||'').replace('#','');
    if(h && window.PRESETS_HASH && PRESETS_HASH[h]){
      var v=PRESETS_HASH[h];
      Object.keys(v).forEach(function(k){root.style.setProperty(k,v[k])});
      var c={p:h,vars:v,fs:(saved&&saved.fs)||''}; save(c); apply(c);
    }
  })();
  if(t){t.addEventListener('click',function(){panel.classList.toggle('open')})}
  if((location.hash||'').indexOf('panel')>=0 && panel){panel.classList.add('open')}

  // 条数密度：每个板块只露前 N 条，其余折叠进「还有 N 条」
  var DKEY='fyb-share-density';
  var dens=localStorage.getItem(DKEY)||document.body.getAttribute('data-limit')||'2';
  if(['1','2','3'].indexOf(dens)<0){dens='2'}
  var dn=document.querySelectorAll('.panel button[data-den]');
  var VIEW='all';
  function layout(){
    var total=0;
    Array.prototype.forEach.call(document.querySelectorAll('section'),function(s){
      var inView=(VIEW==='all')||(s.getAttribute('data-dom')===VIEW);
      s.classList.toggle('hidden-sec',!inView);
      if(!inView){return}
      var open=s.classList.contains('open');
      var arts=s.querySelectorAll('article'), shown=0;
      Array.prototype.forEach.call(arts,function(a){
        var ord=parseInt(a.getAttribute('data-ord'),10)||0;
        var hide=!open && ord>parseInt(dens,10);
        a.classList.toggle('hidden',hide);
        if(!hide){shown++}
      });
      total+=shown;
      var btn=s.querySelector('.more button');      if(btn){
        var rest=arts.length-shown;
        if(rest>0){btn.style.display='';btn.textContent='还有 '+rest+' 条 · 展开'}
        else{btn.style.display='none'}
      }
    });
    var cnt=document.getElementById('cnt');
    if(cnt){cnt.textContent=total+' 条'}
    var mins=document.getElementById('mins');
    if(mins){
      var chars=0;
      Array.prototype.forEach.call(document.querySelectorAll('article:not(.hidden)'),function(a){
        if(a.closest('section.hidden-sec')){return}
        chars+=a.textContent.length;
      });
      mins.textContent=Math.max(1,Math.round(chars/480));
    }
    Array.prototype.forEach.call(dn,function(b){b.dataset.active=(b.dataset.den===dens)?'1':'0'});
  }
  Array.prototype.forEach.call(dn,function(b){
    b.addEventListener('click',function(){
      dens=b.dataset.den;
      try{localStorage.setItem(DKEY,dens)}catch(e){}
      layout();
    });
  });
  document.addEventListener('click',function(e){
    var b=e.target.closest?e.target.closest('.more button'):null;
    if(!b){return}
    var s=b.closest('section');
    if(s){s.classList.add('open');layout()}
  });

  // 领域切换：全部 / 科技AI / 商业财经 / 社会热点 / 生活健康 / 数码娱乐
  var tabs=document.querySelectorAll('.tabs button');
  function setView(v){
    VIEW=v;
    Array.prototype.forEach.call(tabs,function(x){
      x.setAttribute('data-active',x.getAttribute('data-view')===v?'1':'0')
    });
    layout();
  }
  Array.prototype.forEach.call(tabs,function(b){
    b.addEventListener('click',function(){
      setView(b.getAttribute('data-view'));
      window.scrollTo({top:0,behavior:'smooth'});
    });
  });
  // #tech / #life 这类链接可直接打开某个领域
  (function(){
    var h=(location.hash||'').replace('#','');
    if(!h){return}
    Array.prototype.forEach.call(tabs,function(b){
      if(b.getAttribute('data-view')===h){setView(h)}
    });
  })();

  // 自定义背景色：按亮度自动配前景色，保证可读
  var pick=document.getElementById('bgpick'), reset=document.getElementById('bgreset');
  function lum(hex){
    var m=/^#?([a-f\\d]{2})([a-f\\d]{2})([a-f\\d]{2})$/i.exec(hex||'');
    if(!m){return 1}
    var r=parseInt(m[1],16)/255,g=parseInt(m[2],16)/255,b=parseInt(m[3],16)/255;
    return 0.2126*r+0.7152*g+0.0722*b;
  }
  function applyBg(hex){
    var dark=lum(hex)<0.45;
    var v= dark
      ? {'--bg':hex,'--surface':'rgba(255,255,255,.05)','--fg':'#f2ede4','--muted':'#9d968c','--line':'rgba(255,255,255,.14)','--accent':'#d98b5f'}
      : {'--bg':hex,'--surface':'rgba(0,0,0,.03)','--fg':'#1d1b18','--muted':'#7d776d','--line':'rgba(0,0,0,.13)','--accent':'#a8452a'};
    Object.keys(v).forEach(function(k){root.style.setProperty(k,v[k])});
    try{localStorage.setItem(KEY+'-bg',hex)}catch(e){}
  }
  if(pick){
    var savedBg=null;
    try{savedBg=localStorage.getItem(KEY+'-bg')}catch(e){}
    if(savedBg){pick.value=savedBg;applyBg(savedBg)}
    pick.addEventListener('input',function(){applyBg(pick.value)});
  }
  if(reset){
    reset.addEventListener('click',function(){
      try{localStorage.removeItem(KEY+'-bg');localStorage.removeItem(KEY)}catch(e){}
      location.reload();
    });
  }
  layout();
  // 阅读进度
  var bar=document.getElementById('progress');
  function onScroll(){
    var h=document.documentElement.scrollHeight-window.innerHeight;
    bar.style.width=(h>0?(window.scrollY/h*100):0)+'%';
  }
  window.addEventListener('scroll',onScroll,{passive:true});onScroll();
})();
"""


def theme_vars(name: str) -> dict:
    p = PRESETS.get(name) or PRESETS["paper"]
    return {
        "--bg": p["bg"],
        "--surface": p["surface"],
        "--fg": p["fg"],
        "--muted": p["muted"],
        "--line": p["line"],
        "--accent": p["accent"],
    }


def build_css(theme: str) -> str:
    p = PRESETS.get(theme) or PRESETS["paper"]
    kw = {
        "paper": "rgba(168,69,42,.16)",
        "ink": "rgba(47,93,138,.16)",
        "moss": "rgba(77,97,65,.18)",
        "night": "rgba(217,139,95,.22)",
    }.get(theme, "rgba(168,69,42,.16)")
    return (
        CSS.replace("__BG__", p["bg"])
        .replace("__SURFACE__", p["surface"])
        .replace("__FG__", p["fg"])
        .replace("__MUTED__", p["muted"])
        .replace("__LINE__", p["line"])
        .replace("__ACCENT__", p["accent"])
        .replace("__KW__", kw)
    )


# --------------------------------------------------------------------------- #
# 渲染
# --------------------------------------------------------------------------- #
def trim_summary(text: str, keep: int) -> str:
    """只留前 keep 句，压掉信息过载；原文更长时补省略号。"""
    if keep <= 0 or not text:
        return text
    parts = [p for p in re.findall(r"[^。！？!?]*[。！？!?]", text) if p.strip()]
    rest = re.sub(r"[^。！？!?]*[。！？!?]", "", text).strip()
    if len(parts) <= keep:
        return text
    return "".join(parts[:keep]).strip() + "…"


TITLE_PAREN = re.compile(r"^(.*?)[（(]([^（）()]+)[）)]\s*$")


def split_title(raw: str) -> tuple[str, str]:
    """把「英文原标题（中文翻译）」拆成 (中文标题, 英文原标题)。

    只有括号前是纯英文、括号里有中文时才拆；像
    「模组更新｜Mythical Network Cobblemon（118,707 次下载）」这种
    括号前本来就是中文的，整个保留。
    """
    text = (raw or "").strip()
    m = TITLE_PAREN.match(text)
    if m:
        head, tail = m.group(1).strip(), m.group(2).strip()
        head_cjk = bool(re.search(r"[\u4e00-\u9fff]", head))
        tail_cjk = bool(re.search(r"[\u4e00-\u9fff]", tail))
        if not head_cjk and tail_cjk:
            return tail, head
        if head_cjk and not tail_cjk:
            return head, tail
    return text, ""


def render_item(it: dict, kws: list[str], cfg: dict, hidden: bool, ord_: int = 0,
                dom: str = "") -> str:
    cls = "hidden" if hidden else ""
    out = [
        f'<article class="{cls}" data-hit="{1 if it["hits"] else 0}" '
        f'data-ord="{ord_}" data-dom="{html.escape(dom)}">'
    ]
    zh, en = split_title(it["title"])
    if it["hits"]:
        out.append(
            f'<div class="hit">关键词 · {html.escape("、".join(it["hits"]))}<span class="pin">已置顶</span></div>'
        )
    shown = highlight(zh, it["hits"])
    if it.get("link"):
        shown = f'<a href="{html.escape(it["link"], quote=True)}" target="_blank" rel="noopener">{shown}</a>'
    out.append(f"<h3>{shown}</h3>")
    if en:
        out.append(f'<p class="orig">{highlight(en, it["hits"])}</p>')
    if it["summary"]:
        short = trim_summary(it["summary"], int(cfg.get("summary_sentences", 0)))
        out.append(f'<p class="lead">{highlight(short, it["hits"])}</p>')
    if cfg.get("show_points", True) and it["points"]:
        lis = "".join(f"<li>{html.escape(p)}</li>" for p in it["points"])
        out.append(f'<ul class="points">{lis}</ul>')
    if it["comment"]:
        out.append(
            f'<blockquote class="verdict"><span class="who">大肥鱼</span>'
            f'<span class="said">{html.escape(it["comment"])}</span></blockquote>'
        )
    if it["source"] or it["link"]:
        src = html.escape(it["source"])
        if it["link"]:
            src += f' · <a href="{html.escape(it["link"], quote=True)}" target="_blank" rel="noopener">原文</a>'
        out.append(f'<div class="src">{src}</div>')
    out.append("</article>")
    return "".join(out)


def render_html(doc: dict, cfg: dict, *, nav: str = "") -> str:
    kws = [k for k in cfg.get("keywords", []) if k]
    if doc.get("date"):
        kws_all = kws
    else:
        kws_all = kws

    title = cfg.get("site_title", "肥鱼晨报")
    date = doc.get("date") or ""
    weekday = doc.get("weekday") or ""
    mins = reading_minutes(doc, cfg)
    visible_count = sum(
        min(len(s["items"]), s["limit"]) for s in enabled_sections(doc, cfg)
    )

    parts: list[str] = []
    parts.append('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">')
    parts.append('<meta name="viewport" content="width=device-width,initial-scale=1">')
    parts.append(f"<title>{html.escape(title)}{(' · ' + date) if date else ''}</title>")
    parts.append(f"<style>{build_css(cfg.get('theme', 'paper'))}</style>")
    limit_default = max([s["limit"] for s in enabled_sections(doc, cfg)] or [2])
    parts.append(f'</head><body data-limit="{limit_default}">')
    parts.append('<div id="progress"></div><div class="wrap">')

    # 顶栏
    parts.append('<div class="top">')
    parts.append(f'<div class="brand">{html.escape(title)}</div>')
    parts.append('<div class="tools"><button id="tbtn" type="button">外观</button></div>')
    parts.append("</div>")

    swatch_parts = []
    for key, preset in PRESETS.items():
        payload = html.escape(json.dumps(theme_vars(key), ensure_ascii=False), quote=True)
        swatch_parts.append(
            f'<button class="swatch" type="button" data-p="{key}" data-vars="{payload}" '
            f'style="background:{preset["bg"]};border-color:{preset["line"]}" '
            f'title="{preset["label"]}"><i style="background:{preset["accent"]}"></i></button>'
        )
    swatches = "".join(swatch_parts)
    presets_bg = (PRESETS.get(cfg.get("theme", "paper")) or PRESETS["paper"])["bg"]
    parts.append('<div class="panel" id="panel">')
    parts.append(f'<div class="row"><span>配色</span><div style="display:flex;gap:10px">{swatches}</div></div>')
    parts.append(
        '<div class="row"><span>背景</span><div class="bgwrap">'
        f'<input type="color" id="bgpick" value="{presets_bg}" aria-label="自定义背景色">'
        '<button type="button" id="bgreset">恢复</button>'
        "</div></div>"
    )
    parts.append(
        '<div class="row"><span>字号</span><div class="sizewrap">'
        '<button type="button" data-fs="15px">小</button>'
        '<button type="button" data-fs="16px">中</button>'
        '<button type="button" data-fs="17.5px">大</button>'
        "</div></div>"
    )
    parts.append(
        '<div class="row"><span>条数</span><div class="sizewrap">'
        '<button type="button" data-den="1">少</button>'
        '<button type="button" data-den="2">标准</button>'
        '<button type="button" data-den="3">全</button>'
        "</div></div>"
    )
    parts.append("</div>")

    # 标题区
    parts.append("<header>")
    zh_date = ""
    if date:
        try:
            d = dt.date.fromisoformat(date)
            zh_date = f"{d.month} 月 {d.day} 日"
        except ValueError:
            zh_date = date
    parts.append(f"<h1>{html.escape(zh_date or title)}</h1>")
    meta_bits = []
    if date:
        meta_bits.extend([date, f"周{weekday}" if weekday else "", f"约 {mins} 分钟"])
    meta_bits = [b for b in meta_bits if b]
    if meta_bits:
        bits = [html.escape(b) for b in meta_bits]
        if date:
            bits = bits[:-1] + [f'约 <span id="mins">{mins}</span> 分钟'] if bits[-1].startswith("约") else bits
        parts.append(
            f'<div class="date">{" · ".join(bits)} · '
            f'<span id="cnt">{visible_count} 条</span></div>'
        )
    if cfg.get("tagline"):
        parts.append(f'<div class="tagline">{html.escape(cfg["tagline"])}</div>')
    parts.append('<div class="rule"></div>')
    parts.append("</header>")

    # 领域切换（全部 + 各领域）
    secs = enabled_sections(doc, cfg)
    present = {s["id"] for s in secs}
    tabs = ['<nav class="tabs" id="tabs">', '<button type="button" data-view="all" data-active="1">全部</button>']
    for dom_id, dom_name in DOMAINS:
        if dom_id in present:
            tabs.append(f'<button type="button" data-view="{dom_id}">{html.escape(dom_name)}</button>')
    tabs.append("</nav>")
    parts.append("".join(tabs))

    # 板块
    for sec in secs:
        items = sec["items"]
        limit = max(1, sec.get("limit", 2))
        dom = html.escape(sec["id"])
        parts.append(f'<section data-dom="{dom}">')
        parts.append("<div class=\"sechead\">")
        parts.append(f"<h2>{html.escape(sec['name'])}</h2>")
        parts.append(f'<span class="n">{len(items):02d}</span><span class="fill"></span>')
        parts.append("</div>")
        for i, it in enumerate(items):
            parts.append(render_item(it, kws, cfg, hidden=(i + 1) > limit, ord_=i + 1, dom=str(sec["id"])))
        if len(items) > 1:
            rest = max(0, len(items) - limit)
            parts.append(
                f'<div class="more"><button type="button">还有 {rest} 条 · 展开</button></div>'
            )
        parts.append("</section>")

    # 小公告栏
    if cfg.get("show_tips", True) and doc.get("tips"):
        parts.append('<div class="tips"><h2>今日小公告栏</h2>')
        for t in doc["tips"]:
            parts.append('<div class="tip">')
            parts.append(f'<div class="cat">{html.escape(t["category"])}</div>')
            parts.append(f'<div class="txt">{html.escape(t["tip"])}</div>')
            if t["comment"]:
                parts.append(f'<div class="cm">{html.escape(t["comment"])}</div>')
            parts.append("</div>")
        parts.append("</div>")

    parts.append(f"<footer>{html.escape(doc.get('footer') or '大肥鱼简报')}</footer>")
    parts.append("</div>")
    theme_map = {k: theme_vars(k) for k in PRESETS}
    parts.append(
        "<script>window.PRESETS_HASH="
        + json.dumps(theme_map, ensure_ascii=False)
        + ";</script>"
    )
    parts.append(f"<script>{JS}</script>")
    parts.append("</body></html>")
    return "\n".join(parts)


def build_index(cfg: dict) -> Path:
    """写一份「往期列表」索引页，固定地址，天天更新。"""
    files = sorted(SHARE_DIR.glob("肥鱼晨报-*.html"), reverse=True)
    rows = []
    for f in files:
        date = f.stem.replace("肥鱼晨报-", "")
        md = HIST_DIR / f"{date}.md"
        count, fields = "", ""
        if md.exists():
            text = md.read_text("utf-8", errors="ignore")
            m = re.search(r"今日\s*(\d+)\s*条", text)
            if m:
                count = f"{m.group(1)} 条"
            heads = [t.strip() for t in re.findall(r"^##\s+(.+)$", text, re.M) if "公告" not in t]
            fields = " · ".join(heads[:3]) + ("…" if len(heads) > 3 else "")
        try:
            d = dt.date.fromisoformat(date)
            label = f"{d.month} 月 {d.day} 日"
            week = "周" + "一二三四五六日"[d.weekday()]
        except ValueError:
            label, week = date, ""
        rows.append((date, label, week, count, fields, f.name))

    if not rows:
        rows.append(("", "还没有内容", "", "", "", ""))

    t = {k.lstrip('-'): v for k, v in theme_vars(cfg.get("theme", "paper")).items()}
    latest_date, latest_label, latest_week, latest_count, _, latest_file = rows[0]
    items = []
    for date, label, week, count, fields, fname in rows:
        sub = " · ".join(x for x in (week, count, fields) if x)
        items.append(
            f'<li><a href="share/{quote(fname)}"><span class="d">{label}</span>'
            f'<span class="m">{sub}</span></a></li>'
        )

    html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>肥鱼晨报 · 查看往期晨报</title>
<style>
:root{{--bg:{t['bg']};--fg:{t['fg']};--muted:{t['muted']};--line:{t['line']};--accent:{t['accent']}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);
 font:16px/1.75 "Noto Sans SC","PingFang SC","Microsoft YaHei",system-ui,sans-serif;
 -webkit-font-smoothing:antialiased}}
.wrap{{max-width:620px;margin:0 auto;padding:64px 22px 96px}}
.brand{{font-size:12px;letter-spacing:.28em;color:var(--muted)}}
h1{{font-family:"Noto Serif SC","Songti SC",Georgia,serif;font-size:34px;font-weight:600;
 letter-spacing:.04em;margin:26px 0 6px}}
.lead{{color:var(--muted);font-size:14px;margin:0 0 34px}}
.latest{{display:block;text-decoration:none;color:inherit;border:1px solid var(--line);
 border-radius:3px;padding:18px 20px;margin-bottom:40px;transition:border-color .15s}}
.latest:hover{{border-color:var(--accent)}}
.latest .k{{font-size:12px;color:var(--accent);letter-spacing:.1em}}
.latest .n{{font-family:"Noto Serif SC","Songti SC",Georgia,serif;font-size:20px;margin-top:6px}}
.latest .s{{font-size:13px;color:var(--muted);margin-top:4px}}
h2{{font-size:12px;letter-spacing:.2em;color:var(--muted);font-weight:400;
 margin:0 0 8px;padding-bottom:10px;border-bottom:1px solid var(--line)}}
ul{{list-style:none;margin:0;padding:0}}
li a{{display:flex;justify-content:space-between;gap:16px;text-decoration:none;color:inherit;
 padding:12px 2px;border-bottom:1px solid var(--line)}}
li a:hover .d{{color:var(--accent)}}
.d{{font-family:"Noto Serif SC","Songti SC",Georgia,serif;font-size:17px;white-space:nowrap}}
.m{{color:var(--muted);font-size:12.5px;text-align:right;flex:1 1 auto;min-width:0;
 overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
footer{{margin-top:44px;font-size:12px;color:var(--muted);text-align:center}}
</style></head><body><div class="wrap">
<div class="brand">肥鱼晨报</div>
<h1>往期晨报</h1>
<p class="lead">每天早上自动更新，最新一期排在最前。</p>
<a class="latest" href="share/{quote(latest_file)}">
  <div class="k">最新一期</div>
  <div class="n">{latest_label} {latest_week}</div>
  <div class="s">{latest_count or '点开看看'} · 点击阅读</div>
</a>
<h2>全部</h2>
<ul>
{chr(10).join(items)}
</ul>
<footer><a href="./" style="color:inherit;text-decoration:none;border-bottom:1px solid currentColor;opacity:.7">← 返回首页</a> · 十分钟，过一遍今天</footer>
</div></body></html>
"""
    out = BASE_DIR / "docs" / "archive.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, "utf-8")
    return out


def save_outputs(doc: dict, cfg: dict) -> list[Path]:
    """一份内容写三处：工作目录、history/、share/（分享时直接拿 share 里那份）。"""
    blob = render_html(doc, cfg)
    date = doc.get("date") or dt.date.today().isoformat()
    written = []
    for path in (
        BASE_DIR / "早晨简报.html",
        HIST_DIR / f"{date}.html",
        SHARE_DIR / f"肥鱼晨报-{date}.html",
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(blob, "utf-8")
        written.append(path)
    build_index(cfg)
    return written


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
def load_cfg() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            user = json.loads(CONFIG_FILE.read_text("utf-8-sig"))
            cfg.update(user)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] share_config.json 解析失败，用默认配置：{exc}")
    else:
        CONFIG_FILE.write_text(
            json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), "utf-8"
        )
        print(f"[info] 已写出默认配置 {CONFIG_FILE.name}")
    return cfg


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--md", default="")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    cfg = load_cfg()

    if args.all:
        files = sorted(HIST_DIR.glob("*.md"))
        if not files:
            print("[err] history/ 里没有 md")
            return 1
        made = 0
        for f in files:
            doc = parse_markdown(f.read_text("utf-8"))
            written = save_outputs(doc, cfg)
            made += 1
            print(f"[ok] {written[-1].name}")
        print(f"完成 {made} 份")
        return 0

    md_path = Path(args.md) if args.md else (BASE_DIR / "早晨简报.md")
    if not md_path.is_absolute():
        md_path = (BASE_DIR / md_path)
    if not md_path.exists():
        print(f"[err] 找不到 {md_path}")
        return 1
    doc = parse_markdown(md_path.read_text("utf-8"))
    if not doc["sections"]:
        print("[err] 解析不出任何板块，请检查 Markdown 结构")
        return 1
    written = save_outputs(doc, cfg)
    print(f"[ok] {written[0]}  ({written[0].stat().st_size / 1024:.1f} KB)")
    print(f"[ok] 分享用：{written[-1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
