# 大肥鱼 · 每日早晨简报 v2

每天 06:00 自动生成两份简报：

- **新闻版**：5 大领域（科技 AI / 商业财经 / 社会热点 / 生活健康 / 数码娱乐），每领域 2–3 条，外加「今日小公告栏」。
- **学生版**：给高中生的「肥鱼主推」+「小鱼的碎碎念」+「大肥鱼解忧铺」+ 1 道「小试鱼刀」（分步解析、答案与考点）。

网页端是一个选择页，进去后顶栏可互切；电脑关机也照常更新（GitHub Actions 跑）。

## 每条长什么样

- **标题**：中文标题；英文原文标题保留，作为副行小字。
- **核心观点**：200 字左右一段话——发生了什么、关键数字或结论、为什么值得知道。
- **内容摘要**：3–5 条，每条 20–50 字，讲细节（数据、对比、影响）。
- **大肥鱼点评**：70–120 字，用大肥鱼的口气给判断和门道（谁受益、坑在哪、别被什么词忽悠）。
- 来源和「原文」链接放在最后一行，不占正文位置。

全部中文。学术名词、专有名词、型号保留英文原词，后面跟中文解释（比如 `CRISPR（基因编辑技术）`、`H5N1`）。

## 文件说明

| 文件 | 作用 |
|---|---|
| `morning_brief.py` | 新闻版：抓取 → 清洗 → 补摘要 → 翻译/整理 → 渲染 |
| `student_brief.py` | 学生版：知乎热榜 + 教育部 + 豆瓣 → 选 1 条主推 + 3 条碎碎念 + 1 句解忧 + 1 道小题 → 写点评 |
| `questions.json` | 小题题库（九门经典题，可自己加） |
| `comfort.py` | 解忧铺的句子库（古诗文/诸子/谚语，公有领域，34 条，按日期轮换） |
| `docs/theme.js` | 首页与往期页共用的外观面板/密度折叠/领域筛选/阅读进度 |
| `build_web.py` | 把当天 Markdown 转成 `docs/data/*.json`（不联网、不调模型） |
| `render_html.py` | 单文件 HTML 分享版 + `docs/archive.html` 往期存档 |
| `docs/` | 网页端：`index.html` 选择页、`app.js`、`style.css`、`data/` |
| `tips.py` | 小公告栏素材库（90 条，可自己往里加） |
| `run_briefing.bat` | 给计划任务/双击用的一键运行入口 |
| `config.json` | 可选。填 API Key 后启用大模型整理（不填也能跑） |
| `早晨简报.md` / `学生简报.md` | 输出文件，每天覆盖 |
| `history/` / `history_student/` | 按日期存档 |
| `.summary_cache.json` | 整理结果缓存（标题/摘要/要点/点评） |
| `.trans_cache.json` | 翻译缓存，同样的英文句子不会重复翻译 |
| `.seen_links.json` | 三天内不重复的账本 |

## 网页端（`docs/`）

`docs/` 就是 GitHub Pages 发布的那一份，纯静态、零第三方依赖：

- `index.html` 是入口：两个大按钮（新闻简报 / 学生简报），进去后顶栏还能互切。
- 数据来自 `docs/data/news.json`、`docs/data/student.json`，每天由生成脚本重写。
- `docs/archive.html` 是新闻版往期列表（`render_html.py --all` 生成）。
- 本地预览（`docs/data/*.json` 是 fetch 来的，必须走 http，双击 `file://` 打不开）：

```bat
cd /d "C:\Users\AHS\Documents\deepseek-harness\default-workspace\morning_brief"
start "" http://127.0.0.1:8795/docs/index.html
D:\python\python.exe -m http.server 8795
```

## 学生版长什么样

- **肥鱼主推**：1 条必须精选（有热度、好传播、零门槛），含「发生了什么」+ 🐟 大肥鱼点评。
- **小鱼的碎碎念**：3 条贴近高中生日常的话题，每条都有一句话说明「这是什么」+ 点评，不能只有标题。
- **小试鱼刀**：单数日理科、双数日文科，九门轮转、近三天不撞科；优先挑中等难度（计算不难但要动知识点）的题，结构是 题目 → 看解析（折叠，分步详解＋标准答案）→ 考点 → 点评 → 一句建议。
- 铁律：可以抽高考真题，但不许编答案；点评可以「不懂装懂」，但不许胡说。

```bat
D:\python\python.exe student_brief.py          # 生成当天
D:\python\python.exe student_brief.py --force  # 忽略当天已有文件
D:\python\python.exe build_web.py              # 重新生成 docs/data/*.json
```

## 跑一次

双击 `run_briefing.bat`，或者：

```bat
cd /d "C:\Users\AHS\Documents\deepseek-harness\default-workspace\morning_brief"
D:\python\python.exe morning_brief.py
```

- 第一次跑约 60–90 秒（要翻译十几条英文）；之后有缓存，十几秒。
- 强制只用机器翻译（不花 Token）：加 `--no-llm`。

## 翻译与整理怎么工作

1. 抓 RSS / JSON，去掉「Published online / DOI」这类出版元数据；
2. 有的期刊 RSS 只有标题，会去文章页捞摘要，捞不到再抓正文段落；
3. 有 API Key：让模型直接产出中文标题 + 摘要 + 3 条要点 + 点评（质量最好，也最懂学术名词）；
4. 没 Key：走 MyMemory 免费翻译接口翻成中文，再用句子切分提炼摘要与要点；
5. 结果落盘缓存，第二天重复的条目不重复处理。

## 启用大模型整理（可选，推荐）

新建 `config.json`（可复制 `config.example.json` 改名）：

```json
{
  "api_key": "sk-你的key",
  "base_url": "https://api.deepseek.com/v1",
  "model": "deepseek-chat"
}
```

不填 Key 时自动降级到机器翻译，照样能出全中文简报，不报错。
每天 19 条左右，用 `deepseek-chat` 一个月大概几毛钱。

## 每天 06:00 自动跑

### 上线到 GitHub Pages（推荐，电脑可以关机）

完整点击步骤见 **[GitHub上线教程.md](GitHub上线教程.md)**。要点：

- `.github/workflows/daily.yml`：`cron "0 22 * * *"`（UTC）= 北京 06:00，也可在 Actions 页手动 Run
- API key 走仓库 Secret `DAFEIYU_API_KEY`，代码里不落地；`load_config()` 让**环境变量覆盖 config.json**，本地和云端同一套代码
- 每次跑完把新内容提交回仓库（存档 + `.seen_links.json` 去重账本），再发 Pages
- 站点只暴露 `index.html`、`share/*.html`、`history/*.html`，`config.json` 与缓存都在 `.gitignore` 里

### 本机定时（可选，电脑要开机）

以**当前用户**身份执行，不要勾「只在用户登录时运行」以外的选项；电脑 6 点要开机（或从睡眠唤醒）。

```bat
schtasks /Create /TN "大肥鱼早晨简报" /TR "\"C:\Users\AHS\Documents\deepseek-harness\default-workspace\morning_brief\run_briefing.bat\"" /SC DAILY /ST 06:00 /F
```

删除：`schtasks /Delete /TN "大肥鱼早晨简报" /F`

> 注意：Windows 计划任务不会把睡眠中的电脑叫醒，需要的话在「任务计划程序 → 属性 → 条件」里勾选「唤醒计算机运行此任务」。

### 补跑机制（看门狗）

实测 10/29、10/30 两次 06:00 都没触发：现代待机下唤醒计时器唤不醒机器，而「登录时触发」的计划任务需要管理员权限装不上。
现在的方案是 `morning_brief_watchdog.py`：

- 随登录自启（注册表 `HKCU\...\Run` 的「大肥鱼早晨简报补跑」），常驻，每 5 分钟看一眼。
- 6 点后如果 `history/当天.md` 不存在，就补跑 `morning_brief.py`；已存在什么都不做，不花 Token。
- 睡眠唤醒后进程还在，所以「早上开机/唤醒 → 最迟 5 分钟内出简报」。
- 计划任务 06:00 保留作主触发；两边撞车时由 `.running.lock` 单实例锁挡住，不会花两份钱。

- 手动强制重跑：`D:\python\python.exe morning_brief.py --force`
- 看门狗日志：看 `简报运行日志.txt`；它自己跑的时候会自动写进去
- 停掉看门狗：`Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'"` 找到命令行带 watchdog 的进程，`Stop-Process -Id <pid>`
- 彻底卸载自启：`reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "大肥鱼早晨简报补跑" /f`
- 兜底：抓到的条目少于 3 条时判定为网络异常，**不覆盖**上一份简报。

### 三天内不重复（`.seen_links.json`）

抓取窗口是 96 小时，所以昨天的文章今天还会被扫到。程序会记下每条链接的上榜日期，
**3 天内上过的一律跳过**，只把真正没见过的条目交给模型 —— 这就是「每天只处理当天数据」的落地。
账本只留 14 天，文件很小；不想去重就删掉 `.seen_links.json`。

## 想改内容

- 换信息源 / 加板块：改 `morning_brief.py` 顶部的 `SOURCES` 和 `DOMAIN_TITLES`、`DOMAIN_QUOTA`。
- 每个源都带一个 `tier`：1 = 一手/权威（Nature、STAT、CNBC、OpenAI、Mojang 官方…），2 = 垂直好媒体（TechCrunch、Ars、Wired、机核、触乐…），3 = 补充源（雪球、Modrinth、Sky Sports…）。打分时按 4 / 2 / 0.5 加权，越新鲜加分越多（8 小时内 +7，24 小时内 +5），关键词命中再额外加分。
- 同一板块内**每个源只出 1 条**，凑不满才放宽——这样三个位置尽量来自三个不同来源，不会被单一媒体包场。
- 现役 35 个源：科技 AI 8、商业财经 5、社会热点 4、生活健康 7、数码娱乐 11。掉线或停更的源直接删掉即可，不必补位。
- 只认 96 小时内的东西：没有发布时间的条目会先从链接里抠日期（`/2026-10/30/`），抠不到就丢弃，避免把几年前的旧闻当新闻。
- 某板块每天多几条：改 `DOMAIN_QUOTA`。
- 关键词（哪条算这个板块）：`KEYWORDS` 只做加分，不做一票否决。
- 小公告栏：直接往 `tips.py` 的 `TIPS` 里加 `("标签", "内容", "大肥鱼点评")`。
- 语气：改 `llm_summaries()` 里的 system prompt，或 `FALLBACK_COMMENTS`。

## 分享版 HTML（render_html.py）

给朋友看的版本：在 Markdown 之外多出一份**自包含的单文件 HTML**（不联网、不依赖任何资源，双击就能开，也能直接发微信/QQ）。

每天跑完 `morning_brief.py` 会自动生成三份同样的 HTML：

| 位置 | 用途 |
|---|---|
| `早晨简报.html` | 工作目录里随手打开 |
| `history/2026-10-30.html` | 按日期存档 |
| `share/肥鱼晨报-2026-10-30.html` | **分享就发这个**，文件名带日期，不会被覆盖 |
| `index.html` | **往期列表**，每天生成后自动重写；桌面上的「肥鱼晨报」快捷方式指向它 |

每天想直接看最新一期，浏览器收藏这个地址即可（本地文件，不用联网、不用启动服务）：

```
file:///C:/Users/AHS/Documents/deepseek-harness/default-workspace/morning_brief/index.html
```

也可以单独重渲染：

```bat
D:\python\python.exe render_html.py            :: 渲染 早晨简报.md
D:\python\python.exe render_html.py --all      :: 把 history/ 里全部重渲染
```

### 设计取舍（为「十分钟读完」服务）

- 顶部**领域切换**：`全部 / 科技 AI / 商业财经 / 社会热点 / 生活健康 / 数码娱乐`，默认「全部」，滚动时吸在顶上。
- 标题**中文优先**：卡片大标题是中文，英文原标题缩成下面一行小字；原文就是中文的条目不显示英文行。
- 每条四段：**标题 → 核心观点（约 200 字）→ 内容摘要（3–5 条）→ 大肥鱼点评**，来源和原文链接压在最后一行。
- 每个板块默认露 **2 条**，其余收在「还有 N 条 · 展开」后面；「外观」里可整页切「少 / 标准 / 全」（1 / 2 / 3 条一板块）。
- 装饰只做三处：板块标题前的**菱形点**、页脚的一排小圆点、分隔用的发丝线。不加动效、不加背景图，不跟正文抢注意力。
- 顶部一条发丝进度条，读完刚好到底。

### 配置：`share_config.json`

第一次运行会自动生成，改完重新渲染即可。可调项：

| 键 | 说明 |
|---|---|
| `site_title` / `tagline` | 站点名与副标题 |
| `sections` | 领域顺序 + 开关 + 每领域条数（`id` 取 `tech` / `biz` / `society` / `life` / `digital`；`limit` 默认 2） |
| `items_per_section` | 每个领域默认露几条（被 `sections[].limit` 覆盖，读者端的「少 / 标准 / 全」再覆盖它） |
| `keywords` | 关键词表。命中的条目会在本领域内**排到最前**，标上「关键词 · xx 已置顶」，正文淡底高亮 |
| `summary_sentences` | 核心观点保留几句，默认 0（0 = 整段，不做截断） |
| `show_points` | 是否显示内容摘要列表 |
| `show_tips` | 是否显示「今日小公告栏」（分享给别人时关掉） |
| `theme` | 默认配色：`paper`（纸）/ `ink`（墨）/ `moss`（苔）/ `night`（夜） |

### 读者能自己调什么

右上角「外观」里四件事：**4 个配色圆点**、**自定义背景色**（取色器，按亮度自动切换浅/深前景色，保证可读）、**三档字号**、**条数（少 / 标准 / 全）**。选完存进浏览器 localStorage，「恢复」按钮清空。
链接后加 `#night` 打开夜间版，加 `#tech` 直接打开某个领域。

### 分享时的注意事项

- HTML 是纯静态、无脚本外链、无埋点，可直接发文件。
- `config.json` 里的 API Key 只给 `morning_brief.py` 用，**不会**进 HTML。
- 想让朋友每天自己刷新、又不想装软件 —— 下一步可以把这个 HTML 推到 GitHub Pages（需要的话再说）。

## 「大肥鱼点评」这一行

中间一度改成中性的「有什么用」，后来又改回来：栏目叫肥鱼晨报，点评就该有肥鱼的口气，否则跟通稿没区别。

- **写什么**：70–120 字，先给判断（值不值得看、成色如何），再说门道（坑在哪、谁受益、别被什么词忽悠）。
- **不写什么**：不喊口号、不称呼读者、不用第一人称；可以损两句但不刻薄；禁止「值得关注」「意义重大」这类空话。
- **语气来源**：`llm_summaries()` 的 system prompt 定义了「大肥鱼」——一条说话直、有点傲娇、爱吐槽但不刻薄的蓝鲸；`FALLBACK_COMMENTS`（不接模型时的兜底）也按这个调子写。
- **存量内容**：`rewrite_values.py` 可批量改写旧文案，不动新闻本身。

```bat
D:\python\python.exe rewrite_values.py            :: 只改 早晨简报.md
D:\python\python.exe rewrite_values.py --all      :: 连同 history/ 一起
D:\python\python.exe rewrite_values.py --dry-run  :: 只预览，不写文件
```

脚本会顺带更新 `.summary_cache.json`，所以同一条新闻下次再被选中时不会退回旧文案。
