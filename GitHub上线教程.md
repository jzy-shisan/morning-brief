# 把肥鱼晨报搬到 GitHub（小白版）

做完这套操作，你会拿到：

- 一个固定网址：`https://<你的用户名>.github.io/morning-brief/`，手机、电脑、朋友都能打开
- 每天北京时间 **06:00** 自动更新，跑在 GitHub 的免费机器上，**你的电脑可以关机**
- API key 存在 GitHub 的 Secrets 里，网页代码里看不到

预计耗时：**15 分钟**。命令一共 2 条，其余全是点鼠标。

---

## 第 1 步：建一个空仓库（2 分钟）

1. 打开 <https://github.com/new>
2. **Repository name** 填 `morning-brief`
3. 选 **Public**（必须公开，GitHub Pages 免费版只支持公开仓库）
4. 下面三个勾选框（Add a README / .gitignore / license）**全部不要勾**，保持完全空白
5. 点 **Create repository**
6. 复制页面上显示的这一句，等下要用：

   ```
   git remote add origin https://github.com/<你的用户名>/morning-brief.git
   ```

---

## 第 2 步：把代码推上去（推荐：命令行，只需登录一次）

在 `morning_brief` 文件夹里右键 →「在终端中打开」（或打开 PowerShell 后 `cd` 进去），依次执行：

```powershell
git remote add origin https://github.com/<你的用户名>/morning-brief.git
git push -u origin main
```

第一次推送会弹出一个窗口，选 **Sign in with your browser** → 浏览器里点 **Authorize**，之后就再也用管了。

> 卡在 `git push` 一直超时？先把 Watt Toolkit 里的 **GitHub 加速** 打开再重试；还是不行，用文末「附录 A：GitHub Desktop」。
>
> 你电脑上的这个文件夹我已经初始化好了仓库（分支 `main`），所以**不需要** `git init`，也不用管什么 `.gitignore`。

---

## 第 3 步：把 API key 藏进 Secrets（1 分钟）

1. 进入你自己仓库页面 → 顶部 **Settings**
2. 左侧菜单 **Secrets and variables** → **Actions**
3. 点绿色按钮 **New repository secret**
4. 填两栏：
   - **Name**：`DAFEIYU_API_KEY`（一字不差，全大写）
   - **Secret**：你的 `sk-` 开头那串
5. 点 **Add secret**

以后想换 key，就回到这个页面 **Update**。

---

## 第 4 步：打开 Pages（1 分钟）

1. 还在 **Settings** 里 → 左侧 **Pages**
2. **Build and deployment** → **Source** 下拉框选 **GitHub Actions**（⚠️ 不要选 `Deploy from a branch`）
3. 不用点保存，选完就生效

---

## 第 5 步：手动跑一次（验证能通）

1. 仓库顶部 **Actions** 标签
2. 左侧列表点 **每日晨报**
3. 右侧 **Run workflow** → 分支选 `main` → 绿色 **Run workflow**
4. 等 1～2 分钟，刷新页面，出现 **绿色勾** 就成功了
5. 页面顶部会出现一行网址，就是你的固定地址：`https://<用户名>.github.io/morning-brief/`

---

## 第 6 步：检查成果

- 打开网址 → 看到「往期」列表 + 最新一期
- 点进晨报 → 六个领域 tab 能切换、配色/字号能改
- 手机上打开同一个网址也正常

---

## 之后每天会发生什么

`每日晨报` 这个流程在北京时间 06:00 自动执行：

1. 抓取 36 个新闻源 → 生成中文晨报
2. 把新内容**提交回仓库**（存档 + 去重账本）
3. 重新发布网页

两个已知特性（不是 bug）：

- **会晚点**：GitHub 免费版定时任务在高峰期可能延迟 5～30 分钟
- **不会停**：仓库连续 60 天没提交，GitHub 会自动暂停定时任务；我们每天都有提交，所以不受影响

---

## 常见问题对照表

| 你看到的 | 原因 | 怎么办 |
| --- | --- | --- |
| Actions 里没有「每日晨报」 | `.github/workflows/daily.yml` 没推上去（隐藏文件夹容易漏） | 确认仓库里能看到 `.github` 目录；用网页上传多半会漏，见附录 B |
| 运行红叉，日志里 `Permission to ... denied` | 工作流没有写权限 | Settings → Actions → General → **Workflow permissions** 选 **Read and write** → 保存后重跑 |
| 日志里 `api_key` 是空的，或报 401 | Secret 名字不对 | 必须正好是 `DAFEIYU_API_KEY`；改完要重新 Run workflow |
| 网址 404 | 第 4 步没做，或从没成功跑过一次 | 回到第 4、5 步 |
| 链接里出现 `%E8%82%A5...` | 中文文件名被编码，正常 | 直接点链接，不用管 |
| 想加/删新闻源 | —— | 网页打开 `morning_brief.py`，改 `SOURCES` 里那几行 → 提交 → Actions 手动 Run 一次 |

---

## 附录 A：不想用命令行 → GitHub Desktop

1. 装 [GitHub Desktop](https://desktop.github.com/)，用你的账号登录
2. **File → Add local repository** → 选中 `morning_brief` 文件夹
3. 右上角 **Publish repository** → 名字填 `morning-brief` → **取消勾选** `Keep this code private`
4. 发布成功后，回到本文第 3 步继续

---

## 附录 B：只用网页（救急用）

网页的「Upload files」**不支持隐藏文件**（`.github/`、`.gitignore`），所以：

1. 仓库页 → **Add file** → **Create new file**
2. 文件名直接输入 `.github/workflows/daily.yml`（斜杠会自动建目录）
3. 把本仓库 `morning_brief/.github/workflows/daily.yml` 的内容整个粘进去 → Commit
4. 其余 `.py` / `.html` 文件可以用 Upload files 拖进去

---

## 安全提醒

- `config.json` 里是你的 API key，**已经在 `.gitignore` 里**，不会被推上去；别手动改成别的名字再上传
- 万一 key 泄露：去 DeepSeek 控制台吊销、重新生成，然后回来更新 Secret
- 仓库是公开的，所以**不要**把任何私人笔记、日志放进这个文件夹再推上去
