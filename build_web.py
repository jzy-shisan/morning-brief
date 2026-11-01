# -*- coding: utf-8 -*-
"""
把已经生成好的 Markdown 回填成网页数据（不联网、不调模型）。

用法：
    python build_web.py          # 从 早晨简报.md / 学生简报.md 重建 docs/data/*.json
    python build_web.py --all    # 连 history/ 与 history_student/ 也一起重建

用途：
    - 生成脚本已经把 JSON 写好了，这个脚本是「修数据」用的兜底
    - 改了 MD 之后不想重跑抓取，跑它就行
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

import render_html as rh
from morning_brief import BASE_DIR

DOCS_DATA = BASE_DIR / "docs" / "data"
OUT_MD = BASE_DIR / "早晨简报.md"
HIST_DIR = BASE_DIR / "history"
STUDENT_MD = BASE_DIR / "学生简报.md"
STUDENT_HIST = BASE_DIR / "history_student"

TIP_PREFIX = re.compile(r"^(\S+?)\s·\s")


def _trim_title(raw: str) -> str:
    """学生区的标题来自知乎热榜的长问句，展示时压短。"""
    try:
        from student_brief import short_title
        return short_title(raw)
    except Exception:  # noqa: BLE001
        return raw


def _clip(text: str, limit: int = 350) -> str:
    """知乎摘要常是整段转载稿，压到 limit 字以内。"""
    try:
        from student_brief import clip_summary
        return clip_summary(text, limit)
    except Exception:  # noqa: BLE001
        return text


def _blank_item(title: str) -> dict:
    return {
        "title": title,
        "summary": "",
        "points": [],
        "comment": "",
        "source": "",
        "link": "",
        "badge": "",
    }


def _split_title(raw: str) -> tuple[str, str]:
    """把「英文原题（中文译名）」拆成 中文 + 英文。"""
    return rh.split_title(raw)


def news_from_md(md: Path) -> dict | None:
    if not md.exists():
        print(f"跳过（不存在）：{md.name}")
        return None
    doc = rh.parse_markdown(md.read_text("utf-8"))
    sections = []
    for sec in doc["sections"]:
        items = []
        for it in sec["items"]:
            zh, orig = _split_title(it["title"])
            items.append({
                "title": zh,
                "orig": orig,
                "summary": it.get("summary", ""),
                "points": it.get("points", [])[:4],
                "comment": it.get("comment", ""),
                "source": it.get("source", ""),
                "link": it.get("link", ""),
                "badge": "",
            })
        sections.append({"name": sec["name"], "items": items})
    # 小公告栏是给本人看的生活随笔，网页端不放（与分享版 show_tips=false 一致）
    total = sum(len(s["items"]) for s in sections)
    y, mo, d = doc["date"].split("-")
    return {
        "group": "news",
        "date": doc["date"],
        "title": "新闻简报",
        "subtitle": f"{y}年{int(mo)}月{int(d)}日 · 共 {total} 条",
        "sections": sections,
    }


def student_from_md(md: Path) -> dict | None:
    """学生简报结构固定（谈资 + 小题），用轻量解析即可。"""
    if not md.exists():
        print(f"跳过（不存在）：{md.name}")
        return None
    text = md.read_text("utf-8")
    m = re.search(r"学生简报 · (\d{4}-\d{2}-\d{2})", text)
    date = m.group(1) if m else dt.date.today().isoformat()

    talk_items = []
    alt_items = []
    quiz_items = []
    comfort_items = []

    def parse_items(block: str, small: bool) -> list[dict]:
        out = []
        for chunk in re.split(r"^### ", block, flags=re.M)[1:]:
            title, _, rest = chunk.partition("\n")
            it = _blank_item(_trim_title(title.strip()))
            if not it["title"]:
                continue
            sm = re.search(r"^\s*- (.+)$", rest, re.M)
            if sm:
                it["summary"] = _clip(sm.group(1).strip(), 350 if not small else 320)
            cm = re.search(r"> 🐟 \*\*大肥鱼\*\*：(.+)", rest)
            if cm:
                it["comment"] = cm.group(1).strip()
            src = re.search(r"\*来源：(.+?)\*\s*$", rest, re.M)
            if src:
                raw = src.group(1)
                lm = re.search(r"\[看看吧\]\((.+?)\)", raw)
                if lm:
                    it["link"] = lm.group(1).strip()
                    raw = raw.replace(lm.group(0), "")
                parts = [p.strip() for p in raw.split("·") if p.strip()]
                if parts:
                    it["source"] = parts[0]
                if len(parts) > 1:
                    it["badge"] = parts[1]
            it["small"] = small
            out.append(it)
        return out

    cmf_block = re.search(r"^## 🐟 大肥鱼解忧铺\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if cmf_block:
        comfort_items = parse_items(cmf_block.group(1), small=False)
        for it in comfort_items:
            it["small"] = False
            it["points"] = []

    main_block = re.search(r"^## 🐟 肥鱼主推\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if main_block:
        talk_items = parse_items(main_block.group(1), small=False)

    alt_block = re.search(r"^## 🐟 小鱼的碎碎念\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if alt_block:
        alt_items = parse_items(alt_block.group(1), small=True)
    else:
        # 兼容旧版「今日谈资」里的一行式备选
        old = re.search(r"^## 🗣️ 今日谈资\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
        if old and not talk_items:
            talk_items = parse_items(old.group(1), small=False)
            for line in re.findall(r"^- \*\*(.+?)\*\*[^\n]*?——\s*(.+)$", old.group(1), re.M):
                it = _blank_item(_trim_title(line[0].strip()))
                it["comment"] = line[1].strip()
                it["small"] = True
                it["source"] = "知乎热榜"
                alt_items.append(it)

    quiz_block = re.search(r"^## ✏️ (?:一道小题|小试鱼刀)\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if quiz_block:
        body = quiz_block.group(1)
        for chunk in re.split(r"^### ", body, flags=re.M)[1:]:
            title, _, rest = chunk.partition("\n")
            it = _blank_item(title.strip())
            qm = re.search(r"\*\*题目\*\*：(.+)", rest)
            if qm:
                it["question"] = qm.group(1).strip()
            solm = re.search(r"\*\*解析\*\*：\s*\n+\s*(.+?)\n\s*\n", rest, re.S)
            if solm:
                it["solution"] = solm.group(1).strip()
            am = re.search(r"\*\*答案\*\*：\s*\n+\s*(.+?)\n\s*\n", rest, re.S)
            if am:
                it["answer"] = am.group(1).strip()
            pm = re.search(r"\*\*考点\*\*：(.+)", rest)
            if pm:
                it["point"] = pm.group(1).strip()
            cm = re.search(r"> 🐟 \*\*大肥鱼\*\*：(.+)", rest)
            if cm:
                it["comment"] = cm.group(1).strip()
            tm = re.search(r"\*本鱼的建议：(.+?)\*", rest)
            if tm:
                it["tip"] = tm.group(1).strip()
            im = re.search(r"^\*([^*\n].+?)\*\s*$", rest, re.M)
            if im:
                it["summary"] = im.group(1).strip()
            if it["question"]:
                # 「物理 · 经典题型（人工录入）」→ 标题去掉括号，括号里当来源
                paren = re.search(r"[（(]([^（）()]+)[）)]\s*$", it["title"])
                if paren:
                    it["source"] = paren.group(1).strip()
                    it["title"] = it["title"][:paren.start()].strip()
                quiz_items.append(it)

    sections = []
    if talk_items:
        sections.append({"name": "🐟 肥鱼主推", "items": talk_items})
    if alt_items:
        sections.append({"name": "🐟 小鱼的碎碎念", "items": alt_items})
    if comfort_items:
        sections.append({"name": "🐟 大肥鱼解忧铺", "items": comfort_items})
    if quiz_items:
        subject = (quiz_items[0]["title"].split("·")[0] or "").strip() or "综合"
        sections.append({"name": f"✏️ 小试鱼刀 · {subject}", "items": quiz_items})
    d_obj = dt.date.fromisoformat(date)
    pretty = f"{d_obj.year}年{d_obj.month}月{d_obj.day}日"
    return {
        "group": "student",
        "date": date,
        "title": "学生简报",
        "subtitle": pretty,
        "sections": sections,
    }


def write(data: dict | None, name: str) -> None:
    if not data:
        return
    DOCS_DATA.mkdir(parents=True, exist_ok=True)
    path = DOCS_DATA / f"{name}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    print(f"[ok] {path.relative_to(BASE_DIR)}")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="从 Markdown 重建网页数据")
    ap.add_argument("--all", action="store_true", help="连历史目录一起重建")
    args = ap.parse_args()

    write(news_from_md(OUT_MD), "news")
    write(student_from_md(STUDENT_MD), "student")

    if args.all:
        for md in sorted(HIST_DIR.glob("*.md")):
            write(news_from_md(md), f"news-{md.stem}")
        for md in sorted(STUDENT_HIST.glob("*.md")):
            write(student_from_md(md), f"student-{md.stem}")
        print("（历史期已写入 docs/data/，网页端旧版沿用 share/ 的 HTML）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
