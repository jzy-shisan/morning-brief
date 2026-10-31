#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把简报里旧的「大肥鱼点评」整批换成中性的「有什么用」。

用于存量内容的一次性改写：新闻本身没变，只重写每条最后那句价值说明。
会同时更新 .summary_cache.json，避免下次跑到同一条时又变回旧文案。

用法:
    python rewrite_values.py              # 只改 早晨简报.md
    python rewrite_values.py --all        # 连同 history/ 下所有历史
    python rewrite_values.py --dry-run    # 只打印新文案，不落盘
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import morning_brief as mb
import render_html as rh

BASE_DIR = Path(__file__).resolve().parent

SYSTEM = (
    "你是一名严谨的科技新闻编辑，负责为每条新闻写一句「有什么用」。"
    "语言平实、具体、克制：不抒情，不喊口号，不称呼读者，不用第一人称，不评价读者的水平。"
)

TEMPLATE = (
    "为下面每条新闻写一句「有什么用」：30-60 字，具体说明它对读者可能有什么帮助、"
    "能帮他判断什么、或者可以拿来做什么。要落到具体场景，"
    "禁止「值得关注」「意义重大」「不容错过」「干货满满」这类空话；"
    "开头要具体，不要用「可用于」「可据此」「有助于」这类万能开头，同一批里句式不要重复；"
    "不使用「你」「我」「大家」，不评价读者。\n"
    "严格按 JSON 数组输出，不要任何多余文字：\n"
    '[{"i":序号,"v":"有什么用"}]\n\n'
)


def ask_values(cfg: dict, batch: list[dict]) -> dict[int, str]:
    listing = "\n\n".join(
        f"[{i}] 标题：{it['title']}\n摘要：{it['summary']}\n要点：" + "；".join(it["points"])
        for i, it in enumerate(batch)
    )
    raw = mb.llm_request(
        cfg,
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": TEMPLATE + listing}],
    )
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    left, right = raw.find("["), raw.rfind("]")
    data = json.loads(raw[left:right + 1])
    out = {}
    for row in data:
        idx = int(row.get("i", -1))
        text = mb.clean(row.get("v", ""))
        if 0 <= idx < len(batch) and text:
            out[idx] = text
    return out


def collect_items(doc: dict) -> list[dict]:
    return [it for sec in doc["sections"] for it in sec["items"]]


def rewrite_file(path: Path, cfg: dict, dry: bool, force: bool = False) -> int:
    text = path.read_text("utf-8")
    if "> 🐋" not in text and not force:
        print(f"[skip] {path.name} 已经是新格式")
        return 0
    doc = rh.parse_markdown(text)
    items = collect_items(doc)
    if not items:
        print(f"[skip] {path.name} 没有解析出条目")
        return 0

    new_values: dict[str, str] = {}
    for start in range(0, len(items), 5):
        batch = items[start:start + 5]
        try:
            got = ask_values(cfg, batch)
        except Exception as exc:  # noqa: BLE001
            print(f"[err] {path.name} 第 {start // 5 + 1} 批失败：{exc}")
            continue
        for i, it in enumerate(batch):
            if i in got:
                new_values[it["title"]] = got[i]
        print(f"[ok] {path.name} 批次 {start // 5 + 1}: {len(got)} 条")

    if not new_values:
        print(f"[warn] {path.name} 没有拿到任何新文案")
        return 0

    # 逐行替换：跟着 ### 标题走，只动最后那句注释
    lines = text.split("\n")
    out_lines = []
    cur_title = None
    replaced = 0
    for ln in lines:
        m = re.match(r"^###\s+(?:\d+\.\s*)?(.*)$", ln)
        if m:
            cur_title = m.group(1).strip()
        if ln.startswith("> 🐋") or re.match(r"^>\s*\*\*(?:大肥鱼|有什么用)\*\*[：:]", ln):
            if cur_title in new_values:
                out_lines.append(f"> **有什么用**：{new_values[cur_title]}")
                replaced += 1
                continue
        out_lines.append(ln)

    if dry:
        for t, v in list(new_values.items())[:3]:
            print(f"  示例 {t[:24]}… → {v}")
        print(f"[dry] {path.name} 将替换 {replaced} 条")
        return replaced

    path.write_text("\n".join(out_lines), "utf-8")
    print(f"[ok] {path.name} 替换 {replaced} 条")

    # 同步缓存：链接 → 新文案
    cache_file = BASE_DIR / ".summary_cache.json"
    if cache_file.exists():
        cache = json.loads(cache_file.read_text("utf-8"))
        for it in items:
            if it["title"] not in new_values:
                continue
            key = hashlib.sha1(
                (it.get("link") or it["title"]).encode("utf-8")
            ).hexdigest()[:16]
            if key in cache:
                cache[key]["c"] = new_values[it["title"]]
        cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=1), "utf-8")
        print("[ok] 缓存已同步")
    return replaced


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="已经是新格式也重新生成")
    args = ap.parse_args()

    cfg = mb.load_config()
    if not cfg.get("api_key"):
        print("[err] config.json 里没有 api_key")
        return 1

    targets = [BASE_DIR / "早晨简报.md"]
    if args.all:
        targets += sorted(rh.HIST_DIR.glob("*.md"))

    total = 0
    for path in targets:
        if not path.exists():
            continue
        total += rewrite_file(path, cfg, args.dry_run, args.force)

    if not args.dry_run and total:
        for path in targets:
            if path.exists():
                doc = rh.parse_markdown(path.read_text("utf-8"))
                rh.save_outputs(doc, rh.load_cfg())
        print(f"[ok] 共改写 {total} 条，HTML 已重新渲染")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
