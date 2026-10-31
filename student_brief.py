# -*- coding: utf-8 -*-
"""
大肥鱼 · 高中生简报
================================
今日谈资（1 主梗 + 3 备选）+ 一道小题（文/理按单双日轮换，科目九门轮转）

用法：
    python student_brief.py            # 正常生成
    python student_brief.py --no-llm   # 只排版，不调用模型
    python student_brief.py --force    # 今天已生成也重跑

输出：
    学生简报.md                      给主人看的 Markdown
    history_student/YYYY-MM-DD.md    历史留档
    docs/data/student.json           网页端数据
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import urllib.request
from pathlib import Path

from morning_brief import BASE_DIR, load_config, llm_request, log, clean as clean_text


def cfg_ok(cfg: dict | None) -> bool:
    return bool(cfg and cfg.get("api_key"))

HIST_DIR = BASE_DIR / "history_student"
OUT_MD = BASE_DIR / "学生简报.md"
QUESTIONS = BASE_DIR / "questions.json"
DOCS_DATA = BASE_DIR / "docs" / "data"
STUDENT_JSON = DOCS_DATA / "student.json"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# 合规：这些词一票否决，宁缺毋滥
BAD_WORDS = re.compile(r"网传|传言|疑似|爆料|塌房|绯闻|私生活|去世|自杀|血腥|赌博|裸|色情")
# 学生区尽量避开时政硬新闻，有别的就换别的
SOFT_AVOID = re.compile(r"台湾|外交|政治局|军演|制裁|领导人|两会|美方|日方|坦克|导弹|战机|航母|军工")


def short_title(title: str, limit: int = 26) -> str:
    """知乎热榜标题常常是「A，B，C？」，只留最前面那一口气。"""
    text = (title or "").strip()
    cut = min([i for i in (text.find("？"), text.find("?")) if i >= 0] or [len(text)])
    if cut >= 12:
        text = text[:cut]
    parts = [p.strip() for p in re.split(r"[，,；;]", text) if p.strip()]
    out = ""
    for p in parts:
        cand = f"{out}，{p}" if out else p
        if len(cand) > limit and out:
            break
        out = cand
    if len(out) > limit:
        out = out[:limit].rstrip(" ，,、") + "…"
    return out

# 文理与九门
SUBJECTS = {
    "理": ["数学", "物理", "化学", "生物"],
    "文": ["语文", "英语", "政治", "历史", "地理"],
}


# ---------------- 抓取 ----------------
def _get(url: str, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_zhihu(limit: int = 20) -> list[dict]:
    data = json.loads(_get(f"https://api.zhihu.com/topstory/hot-list?limit={limit}").decode("utf-8"))
    out = []
    for row in data.get("data", []):
        t = row.get("target") or {}
        title = short_title(clean_text(t.get("title") or ""))
        if not title:
            continue
        out.append({
            "title": title,
            "text": clean_text(t.get("excerpt") or ""),
            "link": f"https://www.zhihu.com/question/{t.get('id')}" if t.get("id") else "",
            "heat": clean_text(row.get("detail_text") or ""),
            "origin": "知乎热榜",
        })
    return out


_BILI_COOKIE = ""


def bili_cookie() -> str:
    """B站接口不带 buvid3 会返回 -352 风控，先换一枚匿名 cookie。"""
    global _BILI_COOKIE
    if _BILI_COOKIE:
        return _BILI_COOKIE
    try:
        d = json.loads(_get("https://api.bilibili.com/x/frontend/finger/spi").decode("utf-8"))
        b3 = d.get("data", {}).get("b_3", "")
        if b3:
            _BILI_COOKIE = f"buvid3={b3};"
    except Exception:  # noqa: BLE001
        pass
    return _BILI_COOKIE


def fetch_bili(limit: int = 20) -> list[dict]:
    req = urllib.request.Request(
        f"https://api.bilibili.com/x/web-interface/popular?ps={limit}&pn=1",
        headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/", "Cookie": bili_cookie()},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("code") != 0:
        raise RuntimeError(f"B站接口返回 {data.get('code')}")
    out = []
    for v in data.get("data", {}).get("list", []):
        title = clean_text(v.get("title") or "")
        if not title:
            continue
        out.append({
            "title": title,
            "text": clean_text(v.get("desc") or ""),
            "link": f"https://www.bilibili.com/video/{v.get('bvid', '')}",
            "heat": f"{v.get('stat', {}).get('view', 0)} 播放",
            "origin": "B站热门",
        })
    return out


def pick_candidates(*lists: list[dict], limit: int = 8) -> list[dict]:
    """多源交替取，先轻后重：软性话题优先，时政往后放，合规一票否决。"""
    seen, picked, soft = set(), [], []
    for i in range(max(len(lst) for lst in lists)):
        for lst in lists:
            if i >= len(lst):
                continue
            it = lst[i]
            if BAD_WORDS.search(it["title"]) or BAD_WORDS.search(it["text"][:120]):
                continue
            key = re.sub(r"\W+", "", it["title"])[:20]
            if key in seen:
                continue
            seen.add(key)
            (soft if SOFT_AVOID.search(it["title"]) else picked).append(it)
    return (picked + soft)[:limit]


# ---------------- 小题 ----------------
def load_questions() -> list[dict]:
    try:
        return json.loads(QUESTIONS.read_text("utf-8"))
    except Exception:  # noqa: BLE001
        return []


def pick_question(now: dt.datetime) -> dict | None:
    bank = [q for q in load_questions() if q.get("answer")]
    if not bank:
        return None
    # 单数日前理，双数日文
    track = "理" if now.toordinal() % 2 == 1 else "文"
    pool = [q for q in bank if q.get("track") == track] or bank
    # 在池子里按“年内第几天”轮转，保证不总撞同一道
    return pool[now.timetuple().tm_yday % len(pool)]


# ---------------- 模型 ----------------
TALK_SYSTEM = """你是「蓝色大肥鱼」：自称"本鱼"的鲸鱼娘，傲娇、呆萌、嘴硬心软，绝不承认自己胖。
任务：从给定素材里挑 1 条当「今日主梗」，再挑 3 条当「今天可以聊的」。

铁律：
1. 只能使用素材里出现过的事实（人名、数字、事件），一个字都不许编。
2. 拿不准、看不懂的梗就直说"本鱼没看懂"，可以硬着头皮解读，但不能伪造背景知识。
3. 点评要具体针对这条内容，不许写"很有意思""值得关注"这种空话。
4. 语气像赛博宠物：短、俏皮、带一点呆。每条点评 20-45 字。

只输出 JSON：
{"main": {"i": 素材序号, "comment": "点评"}, "others": [{"i": 序号, "comment": "点评"}, ...3条]}
"""

QUIZ_SYSTEM = """你是「蓝色大肥鱼」，要给高中生讲一道题。

铁律：
1. 题目、答案、考点都由系统给定，你必须原样保留，禁止改动、禁止补充新事实。
2. 你的「引子」只能围绕给出的考点展开，可以讲一点常识性背景，但不许编造年份、人物、数据。
3. 点评 25-50 字，俏皮但有用。

只输出 JSON：
{"intro": "两句以内的引子", "comment": "大肥鱼点评", "tip": "一句可执行建议"}
"""


def call_llm(cfg: dict, system: str, user: str) -> dict | None:
    try:
        raw = llm_request(cfg, [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
        m = re.search(r"\{.*\}", raw, re.S)
        return json.loads(m.group(0)) if m else None
    except Exception as exc:  # noqa: BLE001
        log(f"✗ 模型调用失败：{exc}")
        return None


def build_talk(now: dt.datetime, cfg: dict | None, cands: list[dict]) -> dict:
    llm = call_llm(cfg, TALK_SYSTEM, "\n".join(
        f"{i}. [{c['origin']}] {c['title']}｜{c['text'][:160]}｜{c['heat']}" for i, c in enumerate(cands)
    )) if cfg and cands else None

    if llm and isinstance(llm.get("main"), dict) and llm["main"].get("i") is not None:
        i = int(llm["main"]["i"])
        main = dict(cands[i]) if 0 <= i < len(cands) else dict(cands[0])
        main["comment"] = clean_text(llm["main"].get("comment") or "")
        others = []
        for row in llm.get("others", [])[:3]:
            try:
                j = int(row.get("i"))
            except (TypeError, ValueError):
                continue
            if 0 <= j < len(cands) and j != i:
                it = dict(cands[j])
                it["comment"] = clean_text(row.get("comment") or "")
                others.append(it)
        if others:
            return {"main": main, "others": others[:3]}

    # 降级：机械挑选，点评用固定模板（保证不编）
    main = dict(cands[0]) if cands else {"title": "今天没有热梗", "text": "", "link": "", "heat": "", "origin": ""}
    main["comment"] = "本鱼没看懂，但看起来很热闹的样子……主人自己判断吧。"
    others = []
    for it in cands[1:4]:
        it = dict(it)
        it["comment"] = "这条本鱼还没琢磨明白，先记下。"
        others.append(it)
    return {"main": main, "others": others}


def build_quiz(now: dt.datetime, cfg: dict | None) -> dict | None:
    q = pick_question(now)
    if not q:
        return None
    context = (
        f"学科：{q.get('subject')}｜出处：{q.get('source')}\n"
        f"题目：{q.get('question')}\n答案：{q.get('answer')}\n考点：{q.get('point')}\n"
    )
    llm = call_llm(cfg, QUIZ_SYSTEM, context) if cfg else None
    out = dict(q)
    if llm:
        out["intro"] = clean_text(llm.get("intro") or "")
        out["comment"] = clean_text(llm.get("comment") or "")
        out["tip"] = clean_text(llm.get("tip") or "")
    else:
        out["intro"] = ""
        out["comment"] = "这题本鱼会做！……大概吧。"
        out["tip"] = "先自己做一遍，再看答案。"
    return out


# ---------------- 渲染 ----------------
def render(talk: dict, quiz: dict | None, now: dt.datetime, mode: str) -> str:
    d = now.strftime("%Y-%m-%d")
    lines = [
        f"# 🐟 学生简报 · {d}",
        "",
        f"> 大肥鱼出品 · 1 梗 + 1 题 · 整理方式：{mode}",
        "",
        "## 🗣️ 今日谈资",
        "",
        f"### {talk['main']['title']}",
        "",
    ]
    t = talk["main"]
    if t.get("text"):
        lines += ["**发生了什么**", "", f"- {t['text'][:200]}", ""]
    lines += [
        f"> 🐟 **大肥鱼**：{t.get('comment', '')}",
        "",
        f"*来源：{t.get('origin', '')} · {t.get('heat', '')}"
        + (f" · [看看吧]({t['link']})" if t.get("link") else "") + "*",
        "",
    ]
    if talk.get("others"):
        lines += ["**今天还可以聊**", ""]
        for it in talk["others"]:
            lines.append(f"- **{it['title']}** —— {it.get('comment', '')}")
        lines.append("")

    lines += ["## ✏️ 一道小题", ""]
    if quiz:
        lines += [
            f"### {quiz.get('subject', '')} · {quiz.get('source', '')}",
            "",
        ]
        if quiz.get("intro"):
            lines += [f"*{quiz['intro']}*", ""]
        lines += [f"**题目**：{quiz['question']}", "", "**答案**：", "", f"{quiz['answer']}", ""]
        if quiz.get("point"):
            lines += [f"**考点**：{quiz['point']}", ""]
        lines += [f"> 🐟 **大肥鱼**：{quiz.get('comment', '')}", ""]
        if quiz.get("tip"):
            lines += [f"*本鱼的建议：{quiz['tip']}*", ""]
    else:
        lines += ["今天题库空了，本鱼去睡觉了。", ""]
    return "\n".join(lines)


def to_json(talk: dict, quiz: dict | None, now: dt.datetime) -> dict:
    sections = [{
        "name": "🗣️ 今日谈资",
        "items": [{
            "title": talk["main"]["title"],
            "summary": talk["main"].get("text", "")[:300],
            "points": [],
            "comment": talk["main"].get("comment", ""),
            "source": talk["main"].get("origin", ""),
            "link": talk["main"].get("link", ""),
            "badge": talk["main"].get("heat", ""),
        }] + [{
            "title": it["title"],
            "summary": "",
            "points": [],
            "comment": it.get("comment", ""),
            "source": it.get("origin", ""),
            "link": it.get("link", ""),
            "badge": "",
            "small": True,
        } for it in talk.get("others", [])],
    }]
    if quiz:
        subj = quiz.get("subject", "")
        raw = quiz.get("source", "") or "经典题型"
        paren = re.search(r"[（(]([^（）()]+)[）)]\s*$", raw)
        label = raw[:paren.start()].strip() if paren else raw
        origin = paren.group(1).strip() if paren else "题库"
        sections.append({
            "name": f"✏️ 一道小题 · {subj}",
            "items": [{
                "title": f"{subj} · {label}".strip(" ·"),
                "summary": quiz.get("intro", ""),
                "question": quiz["question"],
                "answer": quiz["answer"],
                "point": quiz.get("point", ""),
                "comment": quiz.get("comment", ""),
                "tip": quiz.get("tip", ""),
                "source": origin,
                "link": "",
            }],
        })
    return {
        "group": "student",
        "date": now.strftime("%Y-%m-%d"),
        "title": "学生简报",
        "subtitle": f"{now:%Y年%m月%d日} · 1 梗 + 3 备选 + 1 题",
        "sections": sections,
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    ap = argparse.ArgumentParser(description="生成大肥鱼高中生简报")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    now = dt.datetime.now()
    log("学生简报启动……")

    today = HIST_DIR / f"{now:%Y-%m-%d}.md"
    if not args.force and now.hour >= 6 and today.exists():
        log("今天已经生成过学生简报，跳过（--force 强制重跑）")
        return 0

    cfg = None if args.no_llm else load_config()
    if cfg and not cfg_ok(cfg):
        cfg = None

    zh, bl = [], []
    try:
        zh = fetch_zhihu()
    except Exception as exc:  # noqa: BLE001
        log(f"✗ 知乎抓取失败：{exc}")
    try:
        bl = fetch_bili()
    except Exception as exc:  # noqa: BLE001
        log(f"✗ B站抓取失败：{exc}")
    cands = pick_candidates(zh, bl)
    log(f"候选 {len(cands)} 条（知乎 {len(zh)} / B站 {len(bl)}）")

    if len(cands) < 3 and OUT_MD.exists():
        log("✗ 候选太少，判定网络异常，保留上一份")
        return 1

    talk = build_talk(now, cfg, cands)
    quiz = build_quiz(now, cfg)
    mode = "模型" if cfg else "本地"
    text = render(talk, quiz, now, mode)

    OUT_MD.write_text(text, encoding="utf-8")
    HIST_DIR.mkdir(exist_ok=True)
    today.write_text(text, encoding="utf-8")
    DOCS_DATA.mkdir(parents=True, exist_ok=True)
    STUDENT_JSON.write_text(json.dumps(to_json(talk, quiz, now), ensure_ascii=False, indent=1), "utf-8")

    log(f"✅ 学生简报已生成（{len(text)} 字，{mode}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
