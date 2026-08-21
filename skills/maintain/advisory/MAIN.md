# 投顧知識庫儀表板 · 維護

> **這是正本。** `maintain` 技能裡的 `advisory/MAIN.md` 是它的副本，
> 改動一律先改這一份再整份貼過去。
>
> 上一版停在 2026-08-19／20 重建之前，**而它錯的地方會安靜地成功**：
> repo 根目錄寫 `/Users/kenny/advisory-knowledge-hub`，那份 checkout 還在硬碟上、
> 停在 2026-08-18，讀它不會報錯、只會拿到三天前的東西。
> 2026-08-21 有人照它連過去，拿到舊檔而毫無徵兆。
> 它叫人跑的 `scripts/check.py` 與 `scripts/metrics.py` 也已經不存在。

## 這套系統住在兩個 repo

| | 路徑 | 放什麼 | 誰在推 |
|---|---|---|---|
| 程式與規格 | `/Users/macmini/kb-core` | 門檻、檢查、採集眉角、流程正本 | `com.kenny.kbcorepush`（每 300 秒，帶閘門） |
| 已發布的資料 | `/Users/macmini/advisory-rewrite` | `data/`、Actions 保底層 `raw/`、`sentinel/`、`index.html` | `com.kenny.kbpublish`（每 60 秒） |

**`advisory-knowledge-hub` 是系統 id，不是路徑。** 它寫在資料 repo 根目錄的
`.kb-data-repo` 裡，`publish.py` 拿它做目的地守門，`systems/advisory.py` 拿它
決定跑哪一組檢查。同名的舊 checkout `~/advisory-knowledge-hub` **停在 2026-08-18**，是一個讀得動、不報錯、而且錯得毫無徵兆的陷阱 —— 已於 2026-08-21 搬到 `~/_to_delete/advisory-knowledge-hub-stale-20260818`。
**搬走而不是留著，是因為錯得看得見比錯得安靜好。** 看到它「不存在」是對的。

`com.kenny.kbpublish.plist` 的三個參數是 `(outbox, repo, 系統 id)` ＝
`(~/outbox, ~/advisory-rewrite, advisory-knowledge-hub)`。**看第二個，不要看第三個。**

全程繁體中文（台灣用語），所有路徑寫絕對路徑（與 podcast repo 有多個同名檔案）。
這套系統改動極頻繁：檔案可能在對話進行中被排程或其他對話改掉。
每次動手前重讀當下的檔案，只信這一秒讀到的內容。
Edit 失敗（old_string not found）＝檔案已變，停下重讀。

## 硬規矩

- **不要跑 git 指令去看狀態。** 看檔案用 `cat`／`ls`／`grep`；
  回溯舊版用 Python ＋ zlib 直接讀 `.git/objects`（解析 HEAD → tree → blob，純讀取）；
  看推上去沒有讀 `.git/refs/remotes/origin/main` 與 `.git/logs/HEAD`。
  `com.kenny.kbpublish` 每 60 秒跑一次，任何 git 指令（含 `git status`）
  留下的 `index.lock` 都會擋住它。要實測 git 行為就在 `/tmp` 另建
  bare origin ＋ 工作 repo，**不要拿真 repo 試**。
- **`data/YYYY-MM-DD.json` 只讀不改。** 既有每日封存是歷史，動不得；
  要更正就發新的一天並在 `about.run` 說明。`index.json` 是**衍生狀態**，
  每一輪都由 `publish.py` 重建。
- **批次改文件用精確錨點**：替換前量測 match 長度，改完驗證檔案總長。
- **來源去留只看實際產出紀錄**——手動瀏覽測得通不代表排程通。
- **窗口固定**為前一日台北 07:00 起的滾動 24 小時（值在
  `kb-core/advisory/anchors.json` 的 `window`）。衛星組連續一週三天不足
  → 併回母組（週末不足是常態，看 `weekend_rule`）。
- **這份維護文件不持有會變的值**：門檻、家數、篇幅一律以
  `kb-core/advisory/anchors.json` 為準。上一版違反的正是這一條 ——
  漂掉的不是數字，是路徑與檔名。

## 第 1 步：載入現況

1. Read `/Users/macmini/kb-core/advisory/BRIEF.md`（什麼算對的產出）與
   `advisory/anchors.json`（每一個數字，含 `groups` 那十五組 ——
   **五圖的 `theme` 值域也吃這一份**）。沿革在 `advisory/CHANGELOG.md`，
   **最上面那筆的日期就是你的認知有多舊**。
   讀不到就用 `mcp__cowork__request_cowork_directory` 連 `~/kb-core`、
   `~/advisory-rewrite`、`~/outbox`。
2. Read `/Users/macmini/kb-core/skills/advisory/SKILL.md` —— 每天實際跑的流程正本。
   排程裡那份是副本，兩邊要一致。採集眉角在
   `kb-core/scripts/advisory/preamble.md`。
3. `mcp__scheduled-tasks__list_scheduled_tasks` 找 **`advisory-daily-0730`**
   （舊名 `advisory-dashboard-daily` 已不存在），記下
   cron／enabled／nextRunAt／lastRunAt，並 Read 它的 `path`。
   同帳號另有 podcast、chart 等排程，這一場只碰 advisory 這條。
4. 程式化跑檢查取現況 —— `about.run` 是自述、不是證據
   （2026-08-06 曾自稱有 7 則 Reuters、實際 0 則）：

   ```bash
   python3 /Users/macmini/kb-core/tools/advisory_verify.py /Users/macmini/advisory-rewrite /Users/macmini/advisory-rewrite/data/<日期>.json
   ```

   十七條檢查跑在 `advisory` suite 上，**完全無副作用**。
   輸出與 `about.run` 對照著看：run 說正常但檢查有紅字＝執行者沒發現。
5. Read `/Users/macmini/advisory-rewrite/data/index.json` 看近幾期的
   跨日記憶欄位（`thermo`／`threads`／`watch`／`pulse`／`snap`）。
   檢查會驗結構，但 **thread 代號「沿用」與 watchReview 的「判定誠實度」
   只能人工看**。
6. 看推送鏈有沒有斷（**回執只說到 push 為止，不代表網站更新了**）：
   比對 `/Users/macmini/advisory-rewrite/.git/refs/heads/main` 與
   `.git/refs/remotes/origin/main`，再看 `~/outbox/<日期>.receipt.json`
   的 `exit` 與 `stage`。哨兵的心跳在 `advisory-rewrite/sentinel/heartbeat.json`。

完成條件：六項都有實際輸出在手，沒有一項靠記憶或推論。

## 第 2 步：找漂移

系統的每個意義都有**單一來源**：門檻在 `advisory/anchors.json`、
什麼算對在 `advisory/BRIEF.md`、檢查邏輯在 `checks/advisory.py`、
流程在 `skills/advisory/SKILL.md`、採集眉角在 `scripts/advisory/preamble.md`、
歷史在 `advisory/CHANGELOG.md`。**漂移**＝某個意義偷偷長出第二份。
各檔的權威範圍與 subagent 視野見 [`FILES.md`](FILES.md)。

逐項查，每項給出「相符／漂移／不適用」，判為漂移的要指出兩邊差在哪、哪一邊對：

- **檢查程式有沒有真的讀到它宣稱在讀的東西。** 這是 2026-08-21 在五圖那邊
  抓到的類型：一條檢查讀的欄位名跟產出的欄位名不同，於是它對著兩週封存全綠、
  一個數字都沒讀到，**而 fixture 是同一套字典寫的，所以自檢照樣通過**。
  查法是拿一期真資料手算一遍，跟檢查說的比。
- 排程 prompt 內嵌了任何程式碼或規格表（有＝漂移回去了，改回指向檔案）。
- 各組下限與家數：`anchors.groups` vs `checks/advisory.py` 的 `_group_floors`
  vs `BRIEF.md` 散文。
- 十五組組名：`anchors.groups` 是**值域的唯一的家**，
  五圖的 `chart.theme_unique` 直接讀它 —— **改組名會讓五圖那邊立刻變紅，
  那是設計成這樣的**。
- subagent 分組與配額（排程 prompt vs `BRIEF.md`）。
- `preamble.md` 的黑名單與發稿日曆有沒有跟上來源異動。
- 保底數據卡（`anchors.base_card_groups`）、窗口定義、則數目標、完成時間。
- 跨版去重與 `dedup_exempt`。
- `index.html` 的徽章表 vs `BRIEF.md` —— **從檔案實際解析**；
  已停用的來源代碼應留在 CSS／BADGE 對照裡、只從顯示列拿掉。
- 瀏覽器 HOME deviceId 是否仍在 `list_connected_browsers` 回傳中；
  fallback 必須是排除 WORK，不可用 connectedAt。
- 排程與實裝：`kb-core/launchd/*.plist` vs `~/Library/LaunchAgents/` 裡的副本
  （對帳指令在 `launchd/README.md`）。

姊妹庫匯流條吃的是外部資料（Podcast 與五圖各看自己 `data/index.json` 的 `days[0]`）。
任一格從網頁上消失＝上游介面變了，轉去該系統的 `MAIN.md` 處理
（Podcast → `podcast/`、五圖 → `chart/`），在本 repo 補是補假的。

## 第 3 步：報告現況，再問要改什麼

報排程狀態、`advisory_verify` 結果、`about.run` 對照、
第 2 步的漂移清單（含哪一邊對）、推送鏈兩側的狀態。

完成條件：使用者看完報告、指定了要改什麼，且你把它覆述成一句話得到確認。
**這一步的產出是報告與那句話，不是任何檔案修改。**

## 第 4 步：執行修改

拿到第 3 步的確認之後，讀 [`MODIFY.md`](MODIFY.md) 並照它走。
