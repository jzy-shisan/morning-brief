# -*- coding: utf-8 -*-
"""
大肥鱼 · 每日早晨简报生成器
================================
用法：
    python morning_brief.py            # 正常生成
    python morning_brief.py --no-llm   # 强制只用本地摘要（不花 Token）

可选配置（任选其一）：
    1) 环境变量：DAFEIYU_API_KEY / DAFEIYU_BASE_URL / DAFEIYU_MODEL
    2) 同目录 config.json：{"api_key": "...", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"}
没有 API Key 时会自动降级为本地摘要，程序照常出简报，不会报错。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html as htmllib
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

from tips import TIPS

BASE_DIR = Path(__file__).resolve().parent
OUT_MD = BASE_DIR / "早晨简报.md"
# 硬规矩（主人定的）：history/ 只写不读。
# 每次运行只处理「当天新抓到的条目」，绝不把历史简报拼进 prompt 喂给模型。
# 想加功能也别在这里读 history，否则 token 烧光、饭也吃不上了。
HIST_DIR = BASE_DIR / "history"
CACHE_FILE = BASE_DIR / ".summary_cache.json"
SEEN_FILE = BASE_DIR / ".seen_links.json"
CONFIG_FILE = BASE_DIR / "config.json"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

DOMAIN_ORDER = ["tech", "biz", "society", "life", "digital"]
DOMAIN_TITLES = {
    "tech": "科技 AI",
    "biz": "商业财经",
    "society": "社会热点",
    "life": "生活健康",
    "digital": "数码娱乐",
}
DOMAIN_QUOTA = {"tech": 3, "biz": 3, "society": 3, "life": 3, "digital": 3}

SOURCES = [
    # ── 科技 AI ──────────────────────────────────────────────
    {"name": "OpenAI News", "domain": "tech", "kind": "rss", "tier": 1,
     "url": "https://openai.com/news/rss.xml"},
    {"name": "MIT Tech Review", "domain": "tech", "kind": "rss", "tier": 1,
     "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed/"},
    {"name": "TechCrunch AI", "domain": "tech", "kind": "rss", "tier": 2,
     "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    {"name": "Ars Technica", "domain": "tech", "kind": "rss", "tier": 2,
     "url": "https://feeds.arstechnica.com/arstechnica/technology-lab"},
    {"name": "The Verge", "domain": "tech", "kind": "rss", "tier": 2,
     "url": "https://www.theverge.com/rss/index.xml"},
    {"name": "Wired", "domain": "tech", "kind": "rss", "tier": 2,
     "url": "https://www.wired.com/feed/rss"},
    {"name": "Hugging Face", "domain": "tech", "kind": "rss", "tier": 2,
     "url": "https://huggingface.co/blog/feed.xml"},
    {"name": "量子位", "domain": "tech", "kind": "rss", "tier": 2,
     "url": "https://www.qbitai.com/feed"},
    # ── 商业财经 ──────────────────────────────────────────────
    {"name": "CNBC", "domain": "biz", "kind": "rss", "tier": 1,
     "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html"},
    {"name": "华尔街见闻", "domain": "biz", "kind": "wallstcn", "tier": 2,
     "url": "https://api-one.wallstcn.com/apiv1/content/lives?channel=global-channel&limit=30"},
    {"name": "MarketWatch", "domain": "biz", "kind": "rss", "tier": 2,
     "url": "http://feeds.marketwatch.com/marketwatch/topstories/"},
    {"name": "界面新闻", "domain": "biz", "kind": "rss", "tier": 2,
     "url": "https://a.jiemian.com/index.php?m=article&a=rss"},
    {"name": "雪球", "domain": "biz", "kind": "rss", "tier": 3,
     "url": "https://xueqiu.com/hots/topic/rss"},
    {"name": "Stratechery", "domain": "biz", "kind": "rss", "tier": 2,
     "url": "https://stratechery.com/feed/"},
    # ── 社会热点 ──────────────────────────────────────────────
    {"name": "中新网 · 社会", "domain": "society", "kind": "rss", "tier": 1,
     "url": "https://www.chinanews.com.cn/rss/society.xml"},
    {"name": "中新网 · 要闻", "domain": "society", "kind": "rss", "tier": 1,
     "url": "https://www.chinanews.com.cn/rss/importnews.xml"},
    {"name": "中新网 · 文化", "domain": "society", "kind": "rss", "tier": 1,
     "url": "https://www.chinanews.com.cn/rss/culture.xml"},
    {"name": "中新网 · 国内", "domain": "society", "kind": "rss", "tier": 1,
     "url": "https://www.chinanews.com.cn/rss/china.xml"},
    {"name": "Solidot", "domain": "society", "kind": "rss", "tier": 2,
     "url": "https://www.solidot.org/index.rss"},
    # ── 生活健康 ──────────────────────────────────────────────
    {"name": "Nature", "domain": "life", "kind": "rss", "tier": 1,
     "url": "https://www.nature.com/nature.rss"},
    {"name": "STAT News", "domain": "life", "kind": "rss", "tier": 1,
     "url": "https://www.statnews.com/feed/"},
    {"name": "Nature Biotechnology", "domain": "life", "kind": "rss", "tier": 1,
     "url": "https://www.nature.com/nbt.rss"},
    {"name": "Nature Medicine", "domain": "life", "kind": "rss", "tier": 1,
     "url": "https://www.nature.com/nm.rss"},
    {"name": "Nature Human Behaviour", "domain": "life", "kind": "rss", "tier": 1,
     "url": "https://www.nature.com/nathumbehav.rss"},
    {"name": "ScienceDaily 健康", "domain": "life", "kind": "rss", "tier": 2,
     "url": "https://www.sciencedaily.com/rss/health_medicine.xml"},
    {"name": "ScienceDaily 脑与行为", "domain": "life", "kind": "rss", "tier": 2,
     "url": "https://www.sciencedaily.com/rss/mind_brain.xml"},
    # ── 数码娱乐 ──────────────────────────────────────────────
    {"name": "Mojang 官方", "domain": "digital", "kind": "mojang", "tier": 1, "priority": 1,
     "url": "https://launchercontent.mojang.com/v2/news.json"},
    {"name": "机核", "domain": "digital", "kind": "rss", "tier": 2,
     "url": "https://www.gcores.com/rss"},
    {"name": "IGN", "domain": "digital", "kind": "rss", "tier": 2,
     "url": "https://feeds.ign.com/ign/all"},
    {"name": "GameSpot", "domain": "digital", "kind": "rss", "tier": 2,
     "url": "https://www.gamespot.com/feeds/game-news/"},
    {"name": "游研社", "domain": "digital", "kind": "rss", "tier": 2,
     "url": "https://www.yystv.cn/rss/feed"},
    {"name": "触乐", "domain": "digital", "kind": "rss", "tier": 2,
     "url": "https://www.chuapp.com/feed"},
    {"name": "IT之家", "domain": "digital", "kind": "rss", "tier": 2,
     "url": "https://www.ithome.com/rss/"},
    {"name": "少数派", "domain": "digital", "kind": "rss", "tier": 2,
     "url": "https://sspai.com/feed"},
    {"name": "Minecraft 快照", "domain": "digital", "kind": "javapatch", "tier": 3,
     "url": "https://launchercontent.mojang.com/v2/javaPatchNotes.json"},
    {"name": "Modrinth 模组更新", "domain": "digital", "kind": "modrinth", "tier": 3,
     "url": "https://api.modrinth.com/v2/search?limit=20&index=updated"},
    {"name": "Sky Sports", "domain": "digital", "kind": "rss", "tier": 3,
     "url": "https://www.skysports.com/rss/12040"},
]

KEYWORDS = {
    "tech": re.compile(r"大模型|llm|gpt|claude|gemini|deepseek|qwen|开源|open[- ]?source|模型|model|人工智能|\bai\b|"
                       r"芯片|chip|nvidia|英伟达|算力|agent|智能体|机器人|robot|量子|quantum|算法|algorithm", re.I),
    "biz": re.compile(r"经济|gdp|cpi|财报|earnings|revenue|美联储|fed\b|利率|rate|通胀|inflation|关税|tariff|央行|"
                      r"股市|market|ipo|财政|投资|invest|并购|merger|降息|加息|营收|市值", re.I),
    "society": re.compile(r"教育|高考|升学|招生|学生|学校|教师|政策|监管|法案|regulation|政府|法院|事故|调查|就业|"
                          r"社会|民生|城市|交通|公共|补贴|医保|养老", re.I),
    "life": re.compile(r"健康|医学|medic|疾病|disease|临床|clinical|药物|drug|疫苗|vaccine|基因|gene|crispr|"
                       r"睡眠|sleep|心理|情绪|焦虑|营养|nutrition|运动|exercise|大脑|brain|认知|cognitive|长寿", re.I),
    "digital": re.compile(r"游戏|game|minecraft|mojang|mod\b|模组|主机|playstation|xbox|switch|显卡|gpu|手机|"
                          r"数码|耳机|影视|动漫|电竞|esports|比赛|战队|新作|发售|测评|直播", re.I),
}

EXCLUDE = re.compile(
    r"广告|订阅|优惠|促销|招聘|直播回放|抽奖|赞助|点击下载|app 下载|立即购买|限时特价|"
    r"首发|预售|到手价|领券|领卷|国补|购机|开售|预约|承接|定制服务|接单|价格低廉",
    re.I,
)
EXCLUDE_POLITICS = re.compile(
    r"习近平|总书记|政治局|常委|全国人大|政协委员|国务院常务会议|中央军委|书记处|中纪委|"
    r"党和国家领导人|亲切会见|重要指示|重要批示|贺信|致电",
    re.I,
)
EXCLUDE_EDU = re.compile(
    r"巡视|党建|党史|动员会|党组|纪检监察|主题教育|全会|从严治党|总书记|党委|思想政治|党课|廉政|巡察|"
    r"学习贯彻|讲话精神|主题教育|中央八项规定"
)

FALLBACK_COMMENTS = {
    "tech": ["工具和模型层面的实际变化，动手的人能直接参考。",
             "偏行业方向，能看出哪些技术在升温。",
             "涉及开源与生态，做产品的人更容易用上。"],
    "biz": ["宏观与公司层面的数字，能帮你理解资金往哪走。",
            "偏政策与市场情绪，别据此做短期决策。",
            "行业结构变化，看长期比看单季更有用。"],
    "society": ["政策和公共议题的变化，影响面通常比新闻标题大。",
                "偏制度层面的调整，值得对照自己的处境看。",
                "可作背景了解，不必立刻改变判断。"],
    "life": ["和身体、情绪、日常习惯有关，能直接拿来验证。",
             "偏研究结论，别当医嘱照搬。",
             "生活向信息，用得上就用，用不上知道也行。"],
    "digital": ["游戏与数码圈的实际动态，玩的人会有感觉。",
                "偏产品与生态，买之前值得看一眼。",
                "娱乐向内容，图个知道。"],
}

FALLBACK_HEAD = {
    "tech": "【科技 AI】", "biz": "【商业财经】", "society": "【社会热点】",
    "life": "【生活健康】", "digital": "【数码娱乐】",
}


# ─────────────────────────── 基础工具 ───────────────────────────

LOG_FILE = BASE_DIR / "简报运行日志.txt"


def log(msg: str) -> None:
    line = f"[{dt.datetime.now():%H:%M:%S}] {msg}"
    try:
        print(line, flush=True)
    except Exception:  # noqa: BLE001  pythonw 下没有控制台
        pass
    try:
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:  # noqa: BLE001
        pass


def clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = htmllib.unescape(text)
    text = text.replace("\u3000", " ")
    return re.sub(r"\s+", " ", text).strip()


def http_get(url: str, timeout: int = 15, retries: int = 2) -> bytes:
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "application/rss+xml, application/xml, application/json, text/html;q=0.9, */*;q=0.8",
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt < retries:
                time.sleep(1.5)
    raise last  # type: ignore[misc]


def parse_dt(value: str):
    if not value:
        return None
    value = value.strip()
    try:
        return parsedate_to_datetime(value)
    except Exception:  # noqa: BLE001
        pass
    try:
        d = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return d
    except Exception:  # noqa: BLE001
        pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return dt.datetime.strptime(value[:10], fmt)
        except Exception:  # noqa: BLE001
            continue
    return None


def to_local_naive(d):
    if d is None:
        return None
    if d.tzinfo is not None:
        d = d.astimezone().replace(tzinfo=None)
    return d


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


# ─────────────────────────── 各源解析 ───────────────────────────

def parse_feed(data: bytes) -> list[dict]:
    """解析 RSS 2.0 / Atom，失败时退回正则。"""
    items: list[dict] = []
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return parse_feed_regex(data)

    for node in root.iter():
        if _local(node.tag) not in ("item", "entry"):
            continue
        title, link, text, published = "", "", "", ""
        for child in node:
            key = _local(child.tag)
            if key == "title":
                title = "".join(child.itertext())
            elif key == "link":
                link = child.get("href") or "".join(child.itertext())
            elif key in ("description", "summary", "content", "encoded"):
                text = text or "".join(child.itertext())
            elif key in ("pubdate", "published", "updated", "date"):
                published = published or "".join(child.itertext())
        title, text = clean(title), clean(text)
        if title and (text or link):
            items.append({"title": title, "text": text, "link": link.strip(), "dt": to_local_naive(parse_dt(published))})
    return items


def parse_feed_regex(data: bytes) -> list[dict]:
    raw = data.decode("utf-8", "ignore")
    items = []
    for block in re.findall(r"<(?:item|entry)\b.*?</(?:item|entry)>", raw, re.S | re.I):
        title = re.search(r"<title[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", block, re.S | re.I)
        link = re.search(r'<link[^>]*href="([^"]+)"', block, re.I) or re.search(r"<link[^>]*>(.*?)</link>", block, re.S | re.I)
        desc = re.search(r"<(?:description|summary|content)[^>]*>(.*?)</(?:description|summary|content)>", block, re.S | re.I)
        date = re.search(r"<(?:pubDate|published|updated)[^>]*>(.*?)</", block, re.S | re.I)
        if not title:
            continue
        items.append({
            "title": clean(title.group(1)),
            "text": clean(desc.group(1)) if desc else "",
            "link": clean(link.group(1)) if link else "",
            "dt": to_local_naive(parse_dt(date.group(1))) if date else None,
        })
    return items


def parse_mojang(data: bytes) -> list[dict]:
    payload = json.loads(data.decode("utf-8"))
    out = []
    for entry in payload.get("entries", []):
        if entry.get("tag") not in ("news", "patch_notes"):
            continue
        out.append({
            "title": clean(entry.get("title", "")),
            "text": clean(entry.get("text", "")),
            "link": entry.get("readMoreLink") or "",
            "dt": to_local_naive(parse_dt(entry.get("date", ""))),
        })
    return out


def parse_java_patch(data: bytes) -> list[dict]:
    payload = json.loads(data.decode("utf-8"))
    out = []
    for entry in payload.get("entries", []):
        title = clean(entry.get("title", ""))
        if not title:
            continue
        version = entry.get("version", "")
        kind = entry.get("type", "")
        out.append({
            "title": title,
            "text": f"Java 版 {version}（{kind}）已推送，具体改动见官方补丁说明。",
            "link": "https://launchercontent.mojang.com/v2/" + entry.get("contentPath", ""),
            "dt": to_local_naive(parse_dt(entry.get("date", ""))),
        })
    return out


def parse_modrinth(data: bytes) -> list[dict]:
    payload = json.loads(data.decode("utf-8"))
    out = []
    for hit in payload.get("hits", []):
        downloads = hit.get("downloads", 0) or 0
        if downloads < 20000:
            continue
        out.append({
            "title": f"模组更新｜{clean(hit.get('title', ''))}（{downloads:,} 次下载）",
            "text": clean(hit.get("description", "")),
            "link": f"https://modrinth.com/{hit.get('project_type', 'mod')}/{hit.get('slug', '')}",
            "dt": to_local_naive(parse_dt(hit.get("date_modified", ""))),
        })
    return out


def parse_wallstcn(data: bytes) -> list[dict]:
    payload = json.loads(data.decode("utf-8"))
    out = []
    for item in payload.get("data", {}).get("items", []):
        text = clean(item.get("content_text", "") or item.get("content", ""))
        title = clean(item.get("title", "")) or text[:60]
        if not text:
            continue
        ts = item.get("display_time")
        when = dt.datetime.fromtimestamp(ts) if ts else None
        out.append({
            "title": title,
            "text": text,
            "link": item.get("uri", "") or "https://wallstreetcn.com/live/global",
            "dt": when,
        })
    return out


def parse_moe(data: bytes, base: str = "https://www.moe.gov.cn/jyb_xwfb/s5147/") -> list[dict]:
    html_text = data.decode("utf-8", "ignore")
    out, seen = [], set()
    pattern = re.compile(r'href="([^"]*?(t(20\d{6})_\d+\.html))"[^>]*>(.*?)</a>', re.S)
    for href, _full, ymd, label in pattern.findall(html_text):
        title = clean(label)
        if len(title) < 6 or title in seen or ymd.startswith("2013"):
            continue
        seen.add(title)
        when = dt.datetime.strptime(ymd, "%Y%m%d")
        url = href if href.startswith("http") else urllib.parse.urljoin(base, href)
        out.append({"title": title, "text": "", "link": url, "dt": when})
    return out


def fetch_source(source: dict) -> list[dict]:
    data = http_get(source["url"])
    kind = source["kind"]
    if kind == "rss":
        return parse_feed(data)
    if kind == "mojang":
        return parse_mojang(data)
    if kind == "javapatch":
        return parse_java_patch(data)
    if kind == "modrinth":
        return parse_modrinth(data)
    if kind == "wallstcn":
        return parse_wallstcn(data)
    if kind == "moe":
        return parse_moe(data, source["url"])
    return []


# ─────────────────────────── 过滤 / 排序 ───────────────────────────

def normalize_key(title: str) -> str:
    return re.sub(r"[\s\W_]+", "", title.lower())[:60]


TIER_WEIGHT = {1: 4.0, 2: 2.0, 3: 0.5}


def score_item(item: dict, now: dt.datetime) -> float:
    """越新鲜、来源越权威、关键词越命中、正文越完整，分越高。"""
    blob = f"{item['title']} {item['text']}".lower()
    hits = len(KEYWORDS[item["domain"]].findall(blob))
    title_hit = KEYWORDS[item["domain"]].search(item["title"])
    score = min(hits, 5) * 3.0 + (2.0 if title_hit else 0.0)
    dtv = item.get("dt")
    if dtv:
        age_h = (now - dtv).total_seconds() / 3600
        if age_h <= 8:
            score += 7.0
        elif age_h <= 24:
            score += 5.0
        elif age_h <= 48:
            score += 2.5
        elif age_h <= 72:
            score += 1.0
        else:
            score -= 2.0
    else:
        score += 0.5  # 没日期的，给一点分但排在有日期的后面
    score += min(len(item["text"]), 600) / 600.0
    score += TIER_WEIGHT.get(item.get("tier", 2), 2.0)
    score += item.get("priority", 0)
    return score


LINK_DATE = re.compile(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})")


def date_from_link(url: str) -> dt.datetime | None:
    """新华网这类没有 pubDate 的源，从链接里抠日期（/2026-10/30/）。"""
    m = LINK_DATE.search(url or "")
    if not m:
        return None
    try:
        return dt.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def collect(now: dt.datetime) -> tuple[dict[str, list[dict]], dict]:
    stats = {"total": len(SOURCES), "ok": 0, "failed": []}
    buckets: dict[str, list[dict]] = {d: [] for d in DOMAIN_ORDER}
    seen: set[str] = set()
    recent_links = load_seen()

    for source in SOURCES:
        try:
            items = fetch_source(source)
        except Exception as exc:  # noqa: BLE001
            stats["failed"].append(f"{source['name']}（{type(exc).__name__}）")
            log(f"✗ {source['name']} 抓取失败：{exc}")
            continue
        stats["ok"] += 1

        kept = 0
        for item in items:
            title = item["title"]
            if not title or len(title) < 6 or EXCLUDE.search(title):
                continue
            if EXCLUDE_POLITICS.search(title):
                continue
            if source["domain"] == "society" and EXCLUDE_EDU.search(title):
                continue
            key = normalize_key(title)
            if key in seen:
                continue
            if recent_links and seen_recent(recent_links, item.get("link") or "", now):
                continue
            # 关键词不再一票否决：命中只在打分时加分（见 score_item）

            # 只保留近 96 小时（无日期的视为新鲜；纯日期条目按当天中午算）
            dtv = item.get("dt") or date_from_link(item.get("link") or "")
            if dtv and dtv.hour == 0 and dtv.minute == 0:
                dtv = dtv + dt.timedelta(hours=12)
            if not dtv:
                continue  # 查不到日期的一律不收，避免把几年前的旧闻当新闻
            item["dt"] = dtv
            if (now - dtv).total_seconds() > 96 * 3600:
                continue
            seen.add(key)
            item["domain"] = source["domain"]
            item["source"] = source["name"]
            item["priority"] = source.get("priority", 0)
            item["tier"] = source.get("tier", 2)
            item["score"] = score_item(item, now)
            buckets[source["domain"]].append(item)
            kept += 1
        log(f"✓ {source['name']}：{kept} 条可用")

    selected = {}
    for domain in DOMAIN_ORDER:
        quota = DOMAIN_QUOTA[domain]
        ranked = sorted(buckets[domain], key=lambda x: x["score"], reverse=True)
        picked, per_source, rest = [], {}, []
        for item in ranked:
            if len(picked) >= quota:
                rest.append(item)
                continue
            if per_source.get(item["source"], 0) >= 1:
                rest.append(item)
                continue
            per_source[item["source"]] = per_source.get(item["source"], 0) + 1
            picked.append(item)
        # 不够数时，再按分数从被限流的条目里补
        for item in rest:
            if len(picked) >= quota:
                break
            picked.append(item)
        picked.sort(key=lambda x: x["score"], reverse=True)
        selected[domain] = picked[:quota]
    return selected, stats


# ─────────────────────────── 摘要 ───────────────────────────

def load_config() -> dict:
    """先读 config.json，再用环境变量覆盖（GitHub Actions 里只给环境变量）。"""
    cfg = {"api_key": "", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text("utf-8"))
            for k in cfg:
                if data.get(k):
                    cfg[k] = data[k]
        except Exception as exc:  # noqa: BLE001
            log(f"config.json 读取失败，忽略：{exc}")
    for env, key in (
        ("DAFEIYU_API_KEY", "api_key"),
        ("DEEPSEEK_API_KEY", "api_key"),
        ("OPENAI_API_KEY", "api_key"),
        ("DAFEIYU_BASE_URL", "base_url"),
        ("DEEPSEEK_BASE_URL", "base_url"),
        ("DAFEIYU_MODEL", "model"),
        ("DEEPSEEK_MODEL", "model"),
    ):
        val = os.getenv(env)
        if val:
            cfg[key] = val
    return cfg


def load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text("utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def save_cache(cache: dict) -> None:
    try:
        CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), "utf-8")
    except Exception:  # noqa: BLE001
        pass


def cache_key(item: dict) -> str:
    return hashlib.sha1((item.get("link") or item["title"]).encode("utf-8")).hexdigest()[:16]


# ---- 去重账本：只处理「没见过」的条目，避免昨天上过的文章今天又上一遍 ----
def load_seen() -> dict[str, str]:
    """link -> 最后一次上简报的日期（YYYY-MM-DD）"""
    if SEEN_FILE.exists():
        try:
            return json.loads(SEEN_FILE.read_text("utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def seen_recent(seen: dict[str, str], link: str, now: dt.datetime, days: int = 3) -> bool:
    day = seen.get(link)
    if not day:
        return False
    try:
        when = dt.date.fromisoformat(day)
    except ValueError:
        return False
    return (now.date() - when).days < days


def save_seen(seen: dict[str, str], now: dt.datetime) -> None:
    # 只留最近 14 天，文件不会无限膨胀
    cutoff = now.date() - dt.timedelta(days=14)
    pruned = {}
    for link, day in seen.items():
        try:
            if dt.date.fromisoformat(day) >= cutoff:
                pruned[link] = day
        except ValueError:
            continue
    try:
        SEEN_FILE.write_text(json.dumps(pruned, ensure_ascii=False), "utf-8")
    except Exception:  # noqa: BLE001
        pass


def llm_request(cfg: dict, messages: list[dict], timeout: int = 90) -> str:
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    payload = {"model": cfg["model"], "messages": messages, "temperature": 0.7}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {cfg['api_key']}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


# ─────────────────────────── 翻译与结构化 ───────────────────────────

TRANS_CACHE_FILE = BASE_DIR / ".trans_cache.json"
MT_EMAIL = "dafeiyu@163.com"
CJK_RE = re.compile(r"[\u4e00-\u9fff]")

# 学术/专业名词：保留英文原词，括号里给出中文
GLOSSARY = [
    ("Alzheimer", "阿尔茨海默病"),
    ("Parkinson", "帕金森病"),
    ("Huntington", "亨廷顿病"),
    ("CRISPR", "基因编辑技术"),
    ("mRNA", "信使核糖核酸"),
    ("LLM", "大语言模型"),
    ("AGI", "通用人工智能"),
    ("GPT", "生成式预训练模型"),
    ("GPU", "图形处理器"),
    ("TPU", "张量处理器"),
    ("FDA", "美国食品药品监督管理局"),
    ("IPO", "首次公开募股"),
    ("GDP", "国内生产总值"),
    ("CPI", "消费者物价指数"),
    ("SOFR", "担保隔夜融资利率"),
    ("IORB", "准备金余额利率"),
    ("H5N1", "H5N1 禽流感"),
    ("IP", "知识产权"),
    ("FPS", "第一人称射击"),
    ("DLC", "追加下载内容"),
]


def has_cjk(text: str) -> bool:
    return bool(CJK_RE.search(text or ""))


def apply_glossary(text: str) -> str:
    for en, zh in GLOSSARY:
        if en in text and zh not in text:
            text = text.replace(en, f"{en}（{zh}）")
    return text


def load_trans_cache() -> dict:
    if TRANS_CACHE_FILE.exists():
        try:
            return json.loads(TRANS_CACHE_FILE.read_text("utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def save_trans_cache(cache: dict) -> None:
    try:
        TRANS_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), "utf-8")
    except Exception:  # noqa: BLE001
        pass


def split_for_mt(text: str, limit: int = 420) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks, current = [], ""
    for sentence in sentences:
        if len(current.encode("utf-8")) + len(sentence.encode("utf-8")) > limit and current:
            chunks.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current.strip():
        chunks.append(current.strip())
    return chunks


def mt_translate(text: str) -> str:
    """英译中（MyMemory 免费接口），带本地缓存。失败抛异常，由调用方兜底。"""
    text = clean(text)
    if not text or has_cjk(text):
        return text
    key = hashlib.sha1(text.encode("utf-8")).hexdigest()[:20]
    cache = load_trans_cache()
    if key in cache:
        return cache[key]
    parts = []
    for chunk in split_for_mt(text):
        url = (
            "https://api.mymemory.translated.net/get?q="
            + urllib.parse.quote(chunk)
            + f"&langpair=en|zh-CN&de={MT_EMAIL}"
        )
        raw = http_get(url, timeout=25).decode("utf-8", "ignore")
        data = json.loads(raw)
        translated = htmllib.unescape((data.get("responseData") or {}).get("translatedText") or "").strip()
        if not translated or "MYMEMORY WARNING" in translated.upper():
            raise RuntimeError("翻译接口限流或额度用尽")
        parts.append(translated)
        time.sleep(0.2)
    result = "".join(parts)
    cache[key] = result
    save_trans_cache(cache)
    return result


def gloss_terms(zh: str) -> str:
    """译完后若还残留英文术语，补上括号中文，别让他看不懂。"""
    for en, cn in GLOSSARY:
        if en in cn:  # 中文里本来就带这个英文名，别重复标注
            continue
        if en in zh and cn not in zh:
            zh = zh.replace(en, f"{en}（{cn}）")
    return zh


def title_display(title: str, title_zh: str) -> str:
    """英文标题 →「原标题（中文译名）」；中文标题优先用模型改写后的版本。"""
    title_zh = (title_zh or "").strip()
    if not has_cjk(title):
        return f"{title}（{title_zh}）" if title_zh else title
    # 中文源：模型改写过的标题比原始电讯稿更适合当标题
    if title_zh and len(title_zh) >= 8 and title_zh != title:
        return f"{title}（{title_zh}）" if title_zh not in title else title
    return title


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?；;])\s*|(?<=\.)\s+(?=[A-Z0-9])", text)
    return [p.strip() for p in parts if p.strip()]


META_NOISE_RE = re.compile(
    r"(DOI|doi)\s*[:：]?\s*10\.\d{4,9}/"
    r"|Published online|online (published|posted|first)"
    r"|在线(发布|发表)|发布日期|Published:"
    r"|^\s*(Nature|Science|Cell|Nature Biotechnology|Nature Human Behaviour)\b.{0,30}(2026|2025)\s*年",
    re.I,
)


def is_meta_noise(sentence: str) -> bool:
    return bool(META_NOISE_RE.search(sentence))


def build_local(title_zh: str, body_zh: str) -> tuple[str, list[str]]:
    """没有模型时，用译好的中文正文提炼摘要和要点。"""
    raw = [s.strip() for s in split_sentences(body_zh) if len(s.strip()) >= 10]
    sentences = [s for s in raw if not is_meta_noise(s)]
    if not sentences:
        return "", []
    summary = ""
    for sentence in sentences:
        if len(summary) + len(sentence) > 140:
            break
        summary = f"{summary}{sentence}" if summary else sentence
    if not summary:  # 第一句就超长，截一段
        summary = sentences[0][:130] + "…"
    summary = re.sub(r"^\s*\d+\s*[、.．)）]\s*", "", summary)
    points = []
    for sentence in sentences[1:]:
        if len(points) >= 3:
            break
        piece = re.sub(r"^\s*\d+\s*[、.．)）]\s*", "", sentence)
        piece = re.sub(r"^[A-Za-z]?[、.．)）]\s*", "", piece)
        piece = piece if len(piece) <= 80 else piece[:78] + "…"
        if len(piece) >= 8 and piece not in points:
            points.append(piece)
    return summary, points


def llm_summaries(cfg: dict, items: list[dict]) -> dict[int, dict]:
    """让模型一次性给出：中文标题、摘要、核心要点、点评。"""
    results: dict[int, dict] = {}
    system = (
        "你是一名资深的科技新闻编辑，负责把外文报道整理成中文晨报。"
        "「大肥鱼」是这个栏目的固定主笔：一条蓝色胖鲸鱼，说话直、有点傲娇、爱吐槽但不刻薄，"
        "有自己的判断，不人云亦云，也不喊口号。"
    )
    for start in range(0, len(items), 5):
        chunk = items[start:start + 5]
        listing = "\n\n".join(
            f"[{i}] 原标题：{it['title']}\n正文：{it['text'][:800]}"
            for i, it in enumerate(chunk)
        )
        user = (
            "请把下面每条新闻整理成中文，严格按 JSON 数组输出，不要任何多余文字：\n"
            '[{"i":序号,"t":"中文标题","s":"核心观点","p":["摘要1","摘要2","摘要3"],"c":"大肥鱼点评"}]\n'
            "要求：\n"
            "1) 全部用中文；学术名词、专有名词、型号等保留英文原词，并在后面用括号给出恰当中文，例如 CRISPR（基因编辑技术）、Alzheimer（阿尔茨海默病）；\n"
            "2) t 是中文标题，一句话说清这件事，15-30 字，不要书名号、不要加引号、不要副标题；\n"
            "3) s 是「核心观点」，180-220 字，一段话讲完：发生了什么、关键数字或结论、为什么值得知道。"
            "必须是完整的论述而不是罗列；用中文句子开头，机构名/产品名/人名放在句中或句末括注；\n"
            "4) p 是 3-5 条内容摘要，每条 20-50 字，分点讲清细节（数据、对比、影响），不要和 s 重复；\n"
            "5) c 是「大肥鱼点评」，70-120 字，用大肥鱼的口气：先给判断（值不值得看、成色如何），"
            "再说门道（坑在哪、谁受益、别被什么词忽悠），可以损两句但不刻薄；"
            "禁止「值得关注」「意义重大」「不容错过」这类空话，禁止称呼读者，不用「你/我」；\n"
            "6) 不要出现 markdown 符号。\n\n"
            + listing
        )
        try:
            raw = llm_request(cfg, [{"role": "system", "content": system}, {"role": "user", "content": user}])
            raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            left, right = raw.find("["), raw.rfind("]")
            data = json.loads(raw[left:right + 1])
            for row in data:
                idx = int(row.get("i", -1))
                if 0 <= idx < len(chunk):
                    results[start + idx] = {
                        "t": clean(row.get("t", "")),
                        "s": clean(row.get("s", "")),
                        "p": [clean(x) for x in (row.get("p") or []) if clean(x)][:5],
                        "c": clean(row.get("c", "")),
                    }
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            log(f"✗ 模型整理失败（本批 {len(chunk)} 条）：{msg}")
            if "401" in msg or "403" in msg:
                log("→ API Key 无效或没权限，剩下的批次不再尝试")
                break
    return results


def fallback_comment(item: dict) -> str:
    pool = FALLBACK_COMMENTS[item["domain"]]
    return pool[abs(hash(item["title"])) % len(pool)]


META_DESC_PATTERNS = [
    r'<meta[^>]+name=["\'](?:dc\.description|citation_abstract)["\'][^>]*content=["\']([^"\']{40,})',
    r'<meta[^>]+name=["\'](?:description|twitter:description)["\'][^>]*content=["\']([^"\']{40,})',
    r'<meta[^>]+property=["\']og:description["\'][^>]*content=["\']([^"\']{40,})',
    r'<meta[^>]+content=["\']([^"\']{40,})["\'][^>]+name=["\'](?:description|dc\.description)["\']',
]


def fetch_meta_description(url: str) -> str:
    """很多期刊 RSS 只给标题，摘要得去文章页的 meta description 里捞。"""
    try:
        html = http_get(url, timeout=20).decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        return ""
    for pattern in META_DESC_PATTERNS:
        match = re.search(pattern, html, re.I | re.S)
        if match:
            text = clean(htmllib.unescape(re.sub(r"<[^>]+>", " ", match.group(1))))
            if len(text) > 40:
                return text[:600]
    return ""


def strip_meta(text: str) -> str:
    """去掉「Nature, Published online: ...; doi:...」这类出版元数据，只留正文。"""
    t = text or ""
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(
        r"(?:Published online|Online published|Published|在线发布日期?|在线发表|发表在)[:：]?\s*[^;；.]{0,60}[;；.]?",
        " ",
        t,
        flags=re.I,
    )
    t = re.sub(r"doi\s*[:：]?\s*10\.\d{4,9}/\S+", " ", t, flags=re.I)
    t = re.sub(r"^\s*[A-Z][A-Za-z&\-\. ]{1,25},\s*", " ", t)
    t = re.sub(r"(?<=[.!?])\s*(?:https?://\S+\s*)+", " ", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def fetch_page_paragraphs(url: str, limit: int = 600) -> str:
    """没有 meta description 的老站点（比如教育部），直接抓正文段落。"""
    try:
        html = http_get(url, timeout=20).decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        return ""
    body = re.sub(r"(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", html)
    texts, total = [], 0
    for para in re.findall(r"(?is)<p[^>]*>(.*?)</p>", body):
        text = clean(htmllib.unescape(re.sub(r"<[^>]+>", "", para)))
        if len(text) > 25 and not META_NOISE_RE.search(text):
            texts.append(text)
            total += len(text)
        if total > limit:
            break
    return strip_meta(" ".join(texts))[:limit]


def _usable_body(text: str, title: str) -> bool:
    plain = clean(htmllib.unescape(strip_meta(text or ""))).replace(title, " ")
    return len(plain.strip()) > 80


def fill_missing_text(selected: dict[str, list[dict]]) -> int:
    """先清元数据；正文只剩标题和日期的，再去原文页补一段真正的摘要。"""
    fixed = 0
    for domain in DOMAIN_ORDER:
        for it in selected[domain]:
            it["text"] = strip_meta(it.get("text", ""))
            if not it.get("link") or _usable_body(it["text"], it["title"]):
                continue
            desc = strip_meta(fetch_meta_description(it["link"]))
            if len(desc) <= 60:
                desc = fetch_page_paragraphs(it["link"])
            if len(desc) > 60:
                it["text"] = desc
                fixed += 1
            time.sleep(0.3)
    if fixed:
        log(f"→ 从 {fixed} 篇文章页补到了摘要")
    return fixed


def enrich(selected: dict[str, list[dict]], cfg: dict, use_llm: bool) -> str:
    """补齐 title_zh / summary / points / comment，返回实际使用的方式。"""
    flat = [it for domain in DOMAIN_ORDER for it in selected[domain]]
    if not flat:
        return "本地"

    cache = load_cache()
    llm_ready = bool(cfg["api_key"]) and use_llm

    # 1) 命中缓存的先填上
    todo = []
    for it in flat:
        hit = cache.get(cache_key(it))
        if hit and hit.get("v") == 3 and (hit.get("by") == "llm" or not llm_ready):
            it.update({"title_zh": hit["t"], "summary": hit["s"], "points": hit["p"], "comment": hit["c"]})
        else:
            todo.append(it)

    if not todo:
        return "缓存"

    mode = "本地"
    if llm_ready:
        log(f"→ 调用模型 {cfg['model']} 整理 {len(todo)} 条（分批，最多 5 条/次）")
        got = llm_summaries(cfg, todo)
        ok = 0
        for idx, it in enumerate(todo):
            row = got.get(idx)
            if not row or not row["t"]:
                continue
            it["title_zh"] = row["t"]
            it["summary"] = row["s"]
            it["points"] = row["p"]
            it["comment"] = row["c"] or fallback_comment(it)
            cache[cache_key(it)] = {"v": 3, "by": "llm", "t": row["t"], "s": row["s"], "p": row["p"], "c": it["comment"]}
            ok += 1
        if ok:
            mode = "模型"
            # 模型没覆盖到的条目，用机器翻译补
            rest = [it for it in todo if not it.get("summary")]
            todo = rest
        else:
            log("→ 模型没有返回可用结果，改用机器翻译整理")

    if todo:
        log(f"→ 机器翻译整理 {len(todo)} 条（首次较慢，之后走缓存）")
        failed = 0
        for n, it in enumerate(todo, 1):
            title = it["title"]
            body = it.get("text", "")
            try:
                title_zh = title if has_cjk(title) else gloss_terms(mt_translate(title))
                body_zh = body if has_cjk(body) else gloss_terms(mt_translate(body[:700]))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                it["title_zh"] = title
                it["summary"] = ""
                it["points"] = []
                it["comment"] = fallback_comment(it)
                log(f"  ✗ 第 {n} 条翻译失败：{exc}")
                continue
            summary, points = build_local(title_zh, body_zh)
            it["title_zh"] = title_zh
            it["summary"] = summary
            it["points"] = points
            it["comment"] = fallback_comment(it)
            cache[cache_key(it)] = {"v": 3, "by": "mt", "t": title_zh, "s": summary, "p": points, "c": it["comment"]}
            if n % 5 == 0:
                log(f"  已整理 {n}/{len(todo)} 条")
        if failed == len(todo):
            mode = "原文"
        elif mode != "模型":
            mode = "机器翻译"

    save_cache(cache)
    return mode


# ─────────────────────────── 输出 ───────────────────────────

def pick_tips(day: str, count: int = 2) -> list[tuple[str, str, str]]:
    rng = random.Random(f"dafeiyu-{day}")
    return rng.sample(TIPS, count)


def render(selected: dict[str, list[dict]], stats: dict, tips, now: dt.datetime, mode: str) -> str:
    total = sum(len(v) for v in selected.values())
    weekday = "一二三四五六日"[now.weekday()]
    lines = [
        f"# ☀️ 早晨简报 · {now:%Y-%m-%d} 周{weekday}",
        "",
        f"> 大肥鱼出品 · 今日 {total} 条 · 信息源 {stats['ok']}/{stats['total']} 正常 · "
        f"{'全中文整理' if mode in ('模型', '缓存', '机器翻译') else '部分原文'}",
        "",
    ]

    for domain in DOMAIN_ORDER:
        items = selected[domain]
        lines.append(f"## {DOMAIN_TITLES[domain]}")
        lines.append("")
        if not items:
            lines.append("> 今天这块没什么值得看的，别硬凑。")
            lines.append("")
            continue
        for idx, it in enumerate(items, 1):
            lines.append(f"### {idx}. {title_display(it['title'], it.get('title_zh', ''))}")
            lines.append("")
            if it.get("summary"):
                lines.append(f"**核心观点**：{it['summary']}")
                lines.append("")
            if it.get("points"):
                lines.append("**内容摘要**")
                lines.append("")
                for point in it["points"]:
                    lines.append(f"- {point}")
                lines.append("")
            lines.append(f"> 🐋 **大肥鱼**：{it['comment']}")
            lines.append("")
            source_line = f"*来源：{it['source']}"
            if it.get("link"):
                source_line += f" · [原文]({it['link']})"
            lines.append(source_line + "*")
            lines.append("")

    lines.append("## 💡 今日小公告栏")
    lines.append("")
    for i, (category, tip, comment) in enumerate(tips):
        lines.append(f"> **{category}** · {tip}")
        lines.append(">")
        lines.append(f"> 🐋 {comment}")
        if i != len(tips) - 1:
            lines.append(">")
            lines.append("> ---")
            lines.append(">")
    lines.append("")
    lines.append("---")
    lines.append("")
    meta = f"*生成于 {now:%Y-%m-%d %H:%M} · 大肥鱼简报 v2"
    if stats["failed"]:
        meta += f" · 本次未取到：{'、'.join(stats['failed'])}"
    meta += " · 每天 06:00 自动更新*"
    lines.append(meta)
    lines.append("")
    return "\n".join(lines)


DOCS_DATA = BASE_DIR / "docs" / "data"


def write_web(selected: dict[str, list[dict]], tips, now: dt.datetime) -> Path:
    """给网页端（docs/）用的精简数据，字段和 app.js 对齐。"""
    try:
        from render_html import split_title
    except Exception:  # noqa: BLE001
        split_title = lambda s: (s, "")  # noqa: E731
    sections = []
    for domain in DOMAIN_ORDER:
        items = selected[domain]
        if not items:
            continue
        sections.append({
            "name": DOMAIN_TITLES[domain],
            "items": [{
                "title": split_title(title_display(it["title"], it.get("title_zh", "")))[0],
                "orig": split_title(title_display(it["title"], it.get("title_zh", "")))[1],
                "summary": it.get("summary", ""),
                "points": it.get("points", [])[:4],
                "comment": it.get("comment", ""),
                "source": it.get("source", ""),
                "link": it.get("link", ""),
                "badge": "",
            } for it in items],
        })
    if tips:
        sections.append({
            "name": "💡 今日小公告栏",
            "items": [{
                "title": f"{category} · {tip}",
                "summary": "",
                "points": [],
                "comment": comment,
                "source": "",
                "link": "",
                "badge": "",
                "small": True,
            } for category, tip, comment in tips],
        })
    data = {
        "group": "news",
        "date": now.strftime("%Y-%m-%d"),
        "title": "新闻简报",
        "subtitle": f"{now:%Y年%m月%d日} · 共 {sum(len(v) for v in selected.values())} 条",
        "sections": sections,
    }
    DOCS_DATA.mkdir(parents=True, exist_ok=True)
    path = DOCS_DATA / "news.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    return path


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description="生成大肥鱼每日早晨简报")
    parser.add_argument("--no-llm", action="store_true", help="不调用大模型，只用本地摘要")
    parser.add_argument("--out", default=str(OUT_MD), help="输出文件路径")
    parser.add_argument("--force", action="store_true", help="今天已经生成过也强制重跑")
    args = parser.parse_args()

    now = dt.datetime.now()
    log("大肥鱼简报启动……")

    # 开机补跑/登录补跑时会重复触发：今天已经生成过就跳过，省 token
    today_hist = HIST_DIR / f"{now:%Y-%m-%d}.md"
    if not args.force and now.hour >= 6 and today_hist.exists():
        log("今天已经生成过简报，跳过（要强制重跑加 --force）")
        return 0

    # 单实例锁：计划任务和看门狗可能同时触发，避免花两份钱
    lock = BASE_DIR / ".running.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        try:
            stale = time.time() - lock.stat().st_mtime
        except OSError:
            stale = 0
        if stale < 20 * 60:
            log("另一个实例正在运行，跳过")
            return 0
        log("发现僵死锁（超过 20 分钟），接管")
        lock.unlink(missing_ok=True)
        lock.write_text("")

    try:
        cfg = load_config()
        selected, stats = collect(now)
        total = sum(len(v) for v in selected.values())
        log(f"抓取完成：{stats['ok']}/{stats['total']} 个源正常，可用 {total} 条")

        if total < 3 and Path(args.out).exists():
            log(f"✗ 只抓到 {total} 条，判断为网络异常，保留上一次的简报，不覆盖")
            return 1

        fill_missing_text(selected)

        use_llm = not args.no_llm
        mode = enrich(selected, cfg, use_llm)
        log(f"整理方式：{mode}")

        tips = pick_tips(now.strftime("%Y-%m-%d"))
        text = render(selected, stats, tips, now, mode)

        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")

        HIST_DIR.mkdir(exist_ok=True)
        (HIST_DIR / f"{now:%Y-%m-%d}.md").write_text(text, encoding="utf-8")

        try:
            log(f"✅ 网页数据：{write_web(selected, tips, now).name}")
        except Exception as exc:  # noqa: BLE001
            log(f"⚠ 网页数据写出失败：{exc}")

        # 顺手出一份自包含的分享版 HTML（失败不影响主流程）
        try:
            import render_html as _rh  # noqa: PLC0415  同目录脚本

            _cfg = _rh.load_cfg()
            _doc = _rh.parse_markdown(text)
            _written = _rh.save_outputs(_doc, _cfg)
            log(f"✅ 已生成分享版 HTML：{_written[-1].name}")
        except Exception as exc:  # noqa: BLE001
            log(f"⚠ HTML 渲染失败（Markdown 已正常写出）：{exc}")

        # 记下来，后面 3 天不再重复上这些链接
        recent_links = load_seen()
        for items in selected.values():
            for it in items:
                link = it.get("link") or ""
                if link:
                    recent_links[link] = now.strftime("%Y-%m-%d")
        save_seen(recent_links, now)

        log(f"✅ 已生成：{out}（{len(text)} 字）")
        return 0
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception:  # noqa: BLE001  计划任务里看不到报错窗口，写日志里
        import traceback

        log("✗ 运行失败：\n" + traceback.format_exc())
        raise SystemExit(1)
