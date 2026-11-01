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
import comfort
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
# 段子、测试、追更连载这类不算「谈资」，直接排除
NOISE_WORDS = re.compile(r"【第.{1,3}[集话期]】|选一条路|测一测|测测|你适合|MBTI|性格测试|血型|塔罗|周公解梦")
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
# 教育政策类：命中这些词才算「跟高中生有关的政策」
POLICY_HINT = re.compile(
    r"教育部|教育厅|教育局|国务院|政策|通知|意见|办法|方案|改革|试点|推广|招生|考试|高考|中考|"
    r"课标|教材|课程|假期|寒假|暑假|校历|学期|开学|减负|收费|学籍|升学|录取|专业|学位|"
    r"职业教育|民办|双减|课后服务|劳动教育|心理健康"
)
FUN_HINT = re.compile(r"电影|上映|新书|小说|杂志|剧集|动画|游戏|唱片|专辑|演唱会|展览|漫画|综艺|新番|番剧")
# 教育部网站上的会议/巡视/礼节性新闻，跟学生没关系
MOE_NOISE = re.compile(
    r"巡视|巡视组|党组|党建|动员会|座谈|会见|调研|出席|致辞|讲话|贺信|致信|看望|慰问|视察|"
    r"教师节|表彰|开幕式|闭幕式|研究生|博士|学位委员会|驻外|大使"
)


def _get(url: str, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_moe(limit: int = 6, days: int = 12) -> list[dict]:
    """教育部官网新闻/工作动态：只留与高中生直接相关、且是全国层面的。"""
    from urllib.parse import urljoin

    html = _get("https://www.moe.gov.cn/jyb_xwfb/", timeout=20).decode("utf-8", "ignore")
    pat = re.compile(r'href="([^"]*?/t(20\d{6})_\d+\.html)"[^>]*>\s*([^<]{6,80})\s*<')
    out, seen = [], set()
    today = dt.date.today()
    for href, day, title in pat.findall(html):
        title = clean_text(title)
        if len(title) < 8 or title in seen or MOE_NOISE.search(title):
            continue
        if not POLICY_HINT.search(title):
            continue
        try:
            d = dt.date(int(day[:4]), int(day[4:6]), int(day[6:]))
        except ValueError:
            continue
        if (today - d).days > days:
            continue
        seen.add(title)
        out.append({
            "title": title,
            "text": "",
            "link": urljoin("https://www.moe.gov.cn/jyb_xwfb/", href.replace("./", "")),
            "heat": f"{d.month}月{d.day}日",
            "origin": "教育部",
            "policy": True,
        })
    return out[:limit]


def fetch_douban(limit: int = 5) -> list[dict]:
    """豆瓣正在热映：只取片名 + 评分 + 主演，够写一句「有什么新片」了。"""
    html = _get("https://movie.douban.com/cinema/nowplaying/beijing/", timeout=20).decode("utf-8", "ignore")
    out = []
    pat = re.compile(r'<li[^>]*data-title="([^"]{2,30})"[^>]*data-score="([^"]*)"[^>]*data-actors="([^"]*)"')
    for name, score, actors in pat.findall(html):
        name = clean_text(name)
        if not name:
            continue
        bits = []
        if score and score.strip():
            bits.append(f"豆瓣 {score.strip()} 分")
        if actors:
            bits.append(f"主演 {clean_text(actors).split('/')[0].strip()}")
        note = "正在院线上映" + ("，" + "，".join(bits) if bits else "")
        out.append({
            "title": f"新片上映：《{name}》",
            "text": note + "。",
            "link": "",
            "heat": "豆瓣电影",
            "origin": "豆瓣电影",
            "fun": True,
        })
        if len(out) >= limit:
            break
    return out


def fetch_jiemodui(limit: int = 4) -> list[dict]:
    """芥末堆：教育行业的变动，用来看有没有「影响学生」的政策/行业消息。"""
    import xml.etree.ElementTree as ET

    raw = _get("https://www.jiemodui.com/rss", timeout=20)
    root = ET.fromstring(raw)
    out = []
    for it in root.iter("item"):
        title = clean_text((it.findtext("title") or "").strip())
        desc = clean_text((it.findtext("description") or "").strip())
        link = (it.findtext("link") or "").strip()
        if not title:
            continue
        out.append({
            "title": title,
            "text": desc,
            "link": link,
            "heat": "",
            "origin": "芥末堆",
            "policy": bool(POLICY_HINT.search(title)),
            "industry": True,
        })
        if len(out) >= limit:
            break
    return out


def tidy_excerpt(text: str, title: str = "") -> str:
    """知乎摘要常把来源站点的标题尾巴一起带过来，清掉再给人看。"""
    t = clean_text(text or "")
    t = re.sub(r"_[^_\s]{2,12}$", "", t).strip()          # xxx_腾讯新闻
    t = re.sub(r"\s*[-—－]{1,2}\s*[^-—－]{2,12}$", "", t).strip()  # xxx - 某媒体
    if title:
        core = re.sub(r"\W+", "", title)
        if core and re.sub(r"\W+", "", t).startswith(core):
            t = t[len(title):].lstrip(" ，。、")
    # 末尾没有句末标点的半句，多半是转载标题，砍掉
    if t and t[-1] not in "。！？…”）":
        cut = max(t.rfind(ch) for ch in "。！？")
        if cut >= 20:
            t = t[: cut + 1]
    return t


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
            "text": tidy_excerpt(t.get("excerpt") or "", title),
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
            if NOISE_WORDS.search(it["title"]):
                continue
            key = re.sub(r"\W+", "", it["title"])[:20]
            if key in seen:
                continue
            seen.add(key)
            # 没有正文的（纯音乐、纯视频、只有标题）当不了谈资，排到后面
            thin = len(it.get("text") or "") < 40
            (soft if (SOFT_AVOID.search(it["title"]) or thin) else picked).append(it)
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
任务：从给定素材里挑 1 条当「肥鱼主推」，再挑 3 条当「小鱼的碎碎念」。

选「小鱼的碎碎念」的标准，按权重从高到低：
1. **教育政策/教育改革**（最高权重）：教育部等发布的、影响高中生的政策、假期安排、考试招生调整、试点改革。只要有，必须选 1 条，放在碎碎念第一条。
2. **玩乐**：新电影上映、新书/新杂志发布、游戏动画、行业大变动。
3. **其他对高中生有用的**：学习、校园、生活、健康、就业、身边事。

关于政策类的硬规矩：
- 素材里没有政策，就一条都不要提，绝对不许自己编政策、假期安排或改革方案。
- 只写全国性的、或意义重大的（试点、推广、改革模式）；地方性的小事不要。
- note 只能复述标题里已经写明的事实，不许补充具体数字、生效日期、适用范围等素材里没有的细节。
- 政策类的点评要认真写：说清这条对高中生意味着什么、要注意什么，别卖萌混过去。

选「肥鱼主推」的标准（三条都要满足）：
1. 有热度：大家都在讨论的，不是小众自嗨。
2. 好传播：一句话能讲清楚，适合转发给同学、群里能聊起来。
3. 零门槛：不需要专业背景就能听懂，越"啊？还有这种事"越好。
主推之间还要比一比：对多数高中生「有信息价值」的（科学发现、技术进展、社会大事、升学相关）优先于纯赛事和娱乐八卦；
只有当纯赛事/娱乐的热度明显更高（大约 1.5 倍以上）时，才让它当主推，否则放到碎碎念里。

其余碎碎念要求：
- 必须是"能读懂的事"——有具体事件或结论，不能是纯音乐、纯视频、纯标题帖。
- 三条尽量分散在不同话题上。

铁律：
1. 只能使用素材里出现过的事实（人名、数字、事件），一个字都不许编。
2. 拿不准、看不懂的梗就直说"本鱼没看懂"，可以硬着头皮解读，但不能伪造背景知识。
3. 点评必须抓住这条内容里的具体东西（一个数字、一个物件、一个场景），把话落在这件事上；不许写"很有意思""值得关注""太带劲了""素材有了"这类放之四海皆准的套话。
4. 用贪吃、呆萌的鲸鱼视角说话：把东西比成吃的（月亮像月饼、想啃一口）、怕胖嘴硬、装懂又露怯，但事实一个字都不许编。
4. 语气像赛博宠物：短、俏皮、带一点呆。每条点评 20-45 字。
5. 每条碎碎念必须写 note：用平实的中文 150-200 字把这件事讲完整——背景、经过、结果都要有，让完全没听过的人也能看懂；不许只复述标题，不许写到一半停住，不许空着。

只输出 JSON：
{"main": {"i": 素材序号, "comment": "点评"},
 "policy": {"i": 政策素材序号, "note": "150-200字把事讲完整", "comment": "点评"} 或 null（素材里没有政策就填 null）,
 "others": [{"i": 序号, "note": "150-200字把事讲完整", "comment": "点评"}, ...最多3条]}
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


POLICY_WRITE_SYSTEM = """你是「蓝色大肥鱼」，要给高中生讲清一条教育政策。
铁律：
1. 只能复述给定标题里已经写明的事实，禁止补充数字、日期、适用范围、实施细节——素材里没有的，一个字都不许编。
2. note：150-200 字，平实说清「这条讲的是什么、为什么有这个动作、影响到谁」，把事讲完整，不许只复述标题。
3. comment：40-80 字，认真写——这条对高中生意味着什么、要注意什么；可以带一点本鱼的口气，但不许耍宝糊弄。
只输出 JSON：{"note": "...", "comment": "..."}
"""


def annotate_policy(cfg: dict | None, item: dict) -> dict:
    """模型没选中政策条目时，单独补一次，写 note 与点评。"""
    it = dict(item)
    ctx = f"来源：{it.get('origin', '')}｜日期：{it.get('heat', '')}\n标题：{it['title']}"
    llm = call_llm(cfg, POLICY_WRITE_SYSTEM, ctx) if cfg else None
    if llm and llm.get("note"):
        it["note"] = clean_text(llm.get("note") or "")
        it["comment"] = clean_text(llm.get("comment") or "")
    else:
        it["note"] = f"{it['title']}（{it.get('origin', '')} {it.get('heat', '')}）".strip()
        it["comment"] = "这条跟上学直接相关，本鱼先替主人记一笔。"
    return it


def build_talk(now: dt.datetime, cfg: dict | None, cands: list[dict]) -> dict:
    llm = call_llm(cfg, TALK_SYSTEM, "\n".join(
        f"{i}. [{c['origin']}]{'[政策]' if c.get('policy') else ''} {c['title']}｜{c['text'][:200]}｜{c['heat']}"
        for i, c in enumerate(cands)
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
                it["note"] = clean_text(row.get("note") or "")
                it["comment"] = clean_text(row.get("comment") or "")
                others.append(it)

        # 政策位：素材里有政策就必须有一条，模型漏了就补一次
        policy_row = llm.get("policy")
        policy_item = None
        if isinstance(policy_row, dict) and policy_row.get("i") is not None:
            try:
                k = int(policy_row["i"])
            except (TypeError, ValueError):
                k = -1
            if 0 <= k < len(cands) and cands[k].get("policy"):
                policy_item = dict(cands[k])
                policy_item["note"] = clean_text(policy_row.get("note") or "")
                policy_item["comment"] = clean_text(policy_row.get("comment") or "")
        if policy_item is None:
            pool = [c for c in cands if c.get("policy")]
            if pool:
                policy_item = annotate_policy(cfg, pool[0])
        if policy_item:
            others = [policy_item] + [o for o in others if o["title"] != policy_item["title"]][:2]
        if others:
            return {"main": main, "others": others[:3]}

    # 降级：机械挑选，点评用固定模板（保证不编）
    main = dict(cands[0]) if cands else {"title": "今天没有热梗", "text": "", "link": "", "heat": "", "origin": ""}
    main["comment"] = "本鱼没看懂，但看起来很热闹的样子……主人自己判断吧。"
    others = []
    for it in cands[1:4]:
        it = dict(it)
        it["note"] = clip_summary(it.get("text", ""), 70) or "这事本鱼还没弄明白，先记一笔。"
        it["comment"] = "这条本鱼还没琢磨明白，先记下。"
        others.append(it)
    return {"main": main, "others": others}


COMFORT_SYSTEM = """你是「蓝色大肥鱼」，现在要说一句安慰的话给刷手机的高中生听。
要求：
1. 顺着这句金句本身的意思往下说，不要另起话题。
2. 40-80 字，口吻是呆萌、心软、有点笨拙的鲸鱼，可以拿吃的东西打比方、可以撒娇、可以自嘲胖，但不许喊口号（不要"加油""你可以的""相信自己"这类）。
3. 不评价读者，不说教，不编造与这句话无关的事实。
只输出 JSON：{"comment": "..."}
"""


def build_comfort(cfg: dict | None, now: dt.datetime) -> dict:
    """解忧铺：本地句子库按日期轮换，点评交给模型写成治愈口气。"""
    q = dict(comfort.pick(now.toordinal()))
    comment = ""
    if cfg:
        llm = call_llm(cfg, COMFORT_SYSTEM,
                       f"这句话：{q['q']}\n出处：{q['from']}\n白话意思：{q['gloss']}")
        if llm and llm.get("comment"):
            comment = clean_text(llm.get("comment") or "")
    if not comment:
        comment = "这句话本鱼收在贝壳里了，心里乱的时候拿出来念一遍。"
    q["comment"] = comment
    return q


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
def render(talk: dict, quiz: dict | None, now: dt.datetime, mode: str, comfort_row: dict | None = None) -> str:
    d = now.strftime("%Y-%m-%d")
    lines = [
        f"# 🐟 学生简报 · {d}",
        "",
        f"> 大肥鱼出品 · 整理方式：{mode}",
        "",
        "## 🐟 肥鱼主推",
        "",
        f"### {talk['main']['title']}",
        "",
    ]
    t = talk["main"]
    if t.get("text"):
        lines += ["**发生了什么**", "", f"- {clip_summary(t['text'], 350)}", ""]
    lines += [
        f"> 🐟 **大肥鱼**：{t.get('comment', '')}",
        "",
        f"*来源：{t.get('origin', '')} · {t.get('heat', '')}"
        + (f" · [看看吧]({t['link']})" if t.get("link") else "") + "*",
        "",
    ]
    if talk.get("others"):
        lines += ["## 🐟 小鱼的碎碎念", ""]
        for it in talk["others"]:
            lines += [f"### {it['title']}", ""]
            note = it.get("note") or clip_summary(it.get("text", ""), 70)
            if note:
                lines += [f"- {note}", ""]
            lines += [
                f"> 🐟 **大肥鱼**：{it.get('comment', '')}",
                "",
                f"*来源：{it.get('origin', '')}"
                + (f" · [看看吧]({it['link']})" if it.get("link") else "") + "*",
                "",
            ]

    if comfort_row:
        lines += [
            "## 🐟 大肥鱼解忧铺",
            "",
            f"### {comfort_row['q']}",
            "",
            f"- {comfort_row['gloss']}（{comfort_row['from']}）",
            "",
            f"> 🐟 **大肥鱼**：{comfort_row['comment']}",
            "",
            f"*来源：{comfort_row['from']}*",
            "",
        ]

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


def clip_summary(text: str, limit: int = 200) -> str:
    """知乎的摘要常是整段转载稿，砍到 200 字以内，尽量停在句号上。"""
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    cut = max(t.rfind(ch, 0, limit) for ch in "。！？")
    if cut >= int(limit * 0.55):
        return t[: cut + 1]
    # 没有句末标点就退到最近的逗号，别切出半句话
    soft = max(t.rfind(ch, 0, limit) for ch in "，、；")
    if soft >= int(limit * 0.5):
        return t[:soft].rstrip("，、；") + "…"
    return t[:limit].rstrip("，,、；;") + "…"


def to_json(talk: dict, quiz: dict | None, now: dt.datetime, comfort_row: dict | None = None) -> dict:
    sections = [{
        "name": "🐟 肥鱼主推",
        "items": [{
            "title": talk["main"]["title"],
            "summary": clip_summary(talk["main"].get("text", ""), 350),
            "points": [],
            "comment": talk["main"].get("comment", ""),
            "source": talk["main"].get("origin", ""),
            "link": talk["main"].get("link", ""),
            "badge": talk["main"].get("heat", ""),
        }],
    }]
    if talk.get("others"):
        sections.append({
            "name": "🐟 小鱼的碎碎念",
            "items": [{
                "title": it["title"],
                "summary": clip_summary(it.get("note") or it.get("text", ""), 90),
                "points": [],
                "comment": it.get("comment", ""),
                "source": it.get("origin", ""),
                "link": it.get("link", ""),
                "badge": "",
                "small": True,
            } for it in talk["others"]],
        })
    if comfort_row:
        sections.append({
            "name": "🐟 大肥鱼解忧铺",
            "items": [{
                "title": comfort_row["q"],
                "summary": f"{comfort_row['gloss']}（{comfort_row['from']}）",
                "points": [],
                "comment": comfort_row["comment"],
                "source": comfort_row["from"],
                "link": "",
                "badge": "",
            }],
        })
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
        "subtitle": f"{now:%Y年%m月%d日}",
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

    zh, bl, moe, db, jm = [], [], [], [], []
    try:
        zh = fetch_zhihu()
    except Exception as exc:  # noqa: BLE001
        log(f"✗ 知乎抓取失败：{exc}")
    try:
        bl = fetch_bili()
    except Exception as exc:  # noqa: BLE001
        log(f"✗ B站抓取失败：{exc}")
    try:
        moe = fetch_moe()
    except Exception as exc:  # noqa: BLE001
        log(f"✗ 教育部抓取失败：{exc}")
    try:
        db = fetch_douban()
    except Exception as exc:  # noqa: BLE001
        log(f"✗ 豆瓣抓取失败：{exc}")
    try:
        jm = [c for c in fetch_jiemodui() if c.get("policy")]
    except Exception as exc:  # noqa: BLE001
        log(f"✗ 芥末堆抓取失败：{exc}")

    base = pick_candidates(zh, bl)
    pool = moe[:2] + [c for c in jm if c["title"] not in {x["title"] for x in moe}][:1] + db[:2] + base
    seen_t, cands = set(), []
    for c in pool:
        if c["title"] in seen_t:
            continue
        seen_t.add(c["title"])
        cands.append(c)
    cands = cands[:12]
    log(f"候选 {len(cands)} 条（知乎 {len(zh)} / B站 {len(bl)} / 教育部 {len(moe)} / 豆瓣 {len(db)}）")

    if len(cands) < 3 and OUT_MD.exists():
        log("✗ 候选太少，判定网络异常，保留上一份")
        return 1

    talk = build_talk(now, cfg, cands)
    quiz = build_quiz(now, cfg)
    mode = "模型" if cfg else "本地"
    comfort_row = build_comfort(cfg, now)
    text = render(talk, quiz, now, mode, comfort_row)

    OUT_MD.write_text(text, encoding="utf-8")
    HIST_DIR.mkdir(exist_ok=True)
    today.write_text(text, encoding="utf-8")
    DOCS_DATA.mkdir(parents=True, exist_ok=True)
    STUDENT_JSON.write_text(json.dumps(to_json(talk, quiz, now, comfort_row), ensure_ascii=False, indent=1), "utf-8")

    log(f"✅ 学生简报已生成（{len(text)} 字，{mode}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
