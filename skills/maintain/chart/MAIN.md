# 每日五圖 · 維護

> **這是正本。** `maintain` 技能裡的 `chart/MAIN.md` 是它的副本，
> 改動一律先改這一份再整份貼過去 —— 跟 `kb-core/skills/chart/SKILL.md`
> 與排程那份的關係相同。
>
> 上一版停在 2026-08-20 重建之前：路徑寫 `/Users/kenny`、叫人跑已退休的
> `tools/check_day.py`、還把 `com.kenny.dashpush` 當成活的。
> **一份把退休機制當成活的維護文件，會讓下一個人去修一個不存在的東西。**

## 這套系統住在兩個 repo

| | 路徑 | 放什麼 | 誰在推 |
|---|---|---|---|
| 程式與規格 | `/Users/macmini/kb-core` | 門檻、檢查、取數與出圖程式、流程正本 | `com.kenny.kbcorepush`（每 300 秒，帶閘門） |
| 已發布的資料 | `/Users/macmini/chart-of-the-day` | `data/`、`charts/`、`index.html` | `com.kenny.kbpublish.chart`（每 60 秒） |

**守望鏈（2026-08-21 才補齊）**：哨兵 `sentinel.yml` 每天台北 15:20 跑在 GitHub 上，
看門狗 `com.kenny.kbwatch.chart` 每四小時（00/04/08/12/16/20）在 Mac 上問哨兵還活著沒。
在那之前**兩者都不存在**：兩支既有的 kbwatch 一支看 advisory、一支看 podcast，
而 chart 的哨兵 caller 漏了 `permissions:`，從建立到補上一次都沒成功跑過
（唯一那次是 `startup_failure`）。**沒有心跳跟「哨兵判綠」在遠端看起來都是「沒有紅字」。**

**資料 repo 只放已發布的東西**；門檻是程式的一部分，放進資料 repo 會讓
「改門檻」跟「改資料」混在同一個歷史裡。

上游是投顧知識庫，實際路徑是 **`/Users/macmini/advisory-rewrite`**。
`advisory-knowledge-hub` 是**系統 id 不是路徑**；同名的舊 checkout 停在 2026-08-18，
**讀它不會報錯，只會安靜拿到三天前的題材** —— 2026-08-21 首輪就這樣走錯過一次，
當天已搬到 `~/_to_delete/advisory-knowledge-hub-stale-20260818`。

**真正的根因不是那份舊 checkout，是 `skills/chart/SKILL.md` 第 1 步從來沒有寫路徑。**
唯一寫了路徑的地方是已掛失效橫幅的舊 brief，指的正是那份舊 checkout。
路徑當天補進 SKILL —— **「錯得看得見」跟「知道該去哪」是兩件事，兩件都要做。**

全程繁體中文（台灣用語），所有路徑寫絕對路徑（多 repo 有同名檔案）。
這套系統改動頻繁，檔案可能在對話進行中被排程或其他對話改掉：
每次動手前重讀當下的檔案，只信這一秒讀到的內容。
Edit 失敗（old_string not found）＝檔案已變，停下重讀。

## 硬規矩

- **這份維護文件不持有會變的值**：長度上限、排程時刻、門檻、規則清單一律以
  repo 內文件為準。**上一版違反的正是這一條**，只是漂掉的不是數字而是路徑與檔名。
- **不要跑 git 指令去看狀態。** 看檔案用 `cat`／`ls`／`tail`；
  看推上去沒有讀 `.git/refs/remotes/origin/main` 與 `.git/logs/HEAD`，
  或直接抓 Pages 上的 `data/index.json` 比對。
  三支 `kbpublish` 每 60 秒跑一次，任何 git 指令（含 `git status`）留下的
  `index.lock` 都會擋住它們。要實測 git 行為就在 `/tmp` 另建 bare origin ＋
  工作 repo，**不要拿真 repo 試**。
- **既有 `data/YYYY-MM-DD.json` 只讀。** 發布過就是封存，錯了掛 errata、發新的一天。
  修渲染缺陷的唯一合法工具是 `kb-core/scripts/chart/rebuild_option.py`
  （只重建 option，加 `--png` 重繪圖檔）；**不要用 `render_day.py` 回補舊期** ——
  它會重算 `qa_flags`，跟 `about.run` 已寫的處置對不上。
- **兩個 repo 內都保持零符號連結**：Pages 打包遇到 symlink 會 exit 1、全站停更。
  維護測試要用暫存目錄時，把 symlink 建在 repo **外面**
  （例如輸出資料夾底下），結束前 `find . -type l -not -path './.git/*'` 對兩個 repo 各跑一次。
- **驗證看完整輸出與 exit code** —— 這類失敗是安靜的，grep 過濾會把 crash 偽裝成通過。
- **新的硬性檢查規則一律帶生效日**（`known_exceptions.diversity_from` 那種寫法），
  舊期不列入；對舊期硬失敗只會讓人習慣忽略紅字。
- **進每日關鍵路徑的程式碼都先實測過**：合成測試驗得了邏輯、驗不出資料的真實形狀。
- **給使用者的終端指令寫成單行純指令**（zsh 互動模式吃不下行尾 `#` 註解）。

## 第 1 步：載入現況

1. Read `/Users/macmini/kb-core/chart/BRIEF.md`（什麼算對的產出）與
   `chart/anchors.json`（每一個數字）。沿革在 `chart/CHANGELOG.md`，
   **最上面那一筆的日期就是你的認知有多舊**。
   取數眉角在 `chart/SOURCES.md`，第 3 步才需要。
   讀不到就用 `mcp__cowork__request_cowork_directory` 連 `~/kb-core`、
   `~/chart-of-the-day`、`~/outbox`，需要看上游再加 `~/advisory-rewrite`。
2. Read `/Users/macmini/kb-core/skills/chart/SKILL.md` —— 每天實際跑的流程正本。
   排程裡那份是副本，兩邊要一致。
3. `mcp__scheduled-tasks__list_scheduled_tasks` 找 chart 那條，
   記下 cron／enabled／nextRunAt／lastRunAt，並 Read 它的 `path`。
   同帳號另有投顧、podcast 等排程，這一場只碰 chart 這條。
4. Read `/Users/macmini/chart-of-the-day/data/index.json`：
   近幾期的 `themes` 與 `kinds` 分布（同 theme 連續多天＝選題僵化；
   `kinds` 只有 `timeseries`＝多樣性規則失效）。
   **注意 index 有兩種方言**：08-20 之前的 entry 有 `slots` 沒有 `kinds`，
   之後的相反。舊 entry 不回頭改寫。
5. 程式化跑發布前檢查取現況 —— `about.run` 是自述、不是證據：

   ```bash
   python3 /Users/macmini/kb-core/tools/chart_verify.py /Users/macmini/chart-of-the-day
   ```

   不帶日期＝當天，帶 `YYYY-MM-DD` 可診斷舊期，**完全無副作用**。
   舊期紅字先看是不是 `anchors.known_exceptions` 裡登錄過的 —— 是就照原樣留著。
   **回測舊期時 `chart.series_freshness` 一定紅**：它的 `now` 取執行當下，
   不是那一期的日期。那是這條檢查的形狀，不是舊期壞掉。
6. 看推送鏈有沒有斷（**這一項不能靠回執，回執只說到 push 為止**）：

   ```bash
   cat /Users/macmini/chart-of-the-day/.git/refs/remotes/origin/main
   ```

   跟 `.git/refs/heads/main` 比對，再抓
   `https://gundamnboy.github.io/chart-of-the-day/data/index.json` 看
   `days[0].date` 與 `updatedLabel`。
   `kb-core` 那一側讀 `/Users/macmini/kb-core/.push-receipt.json`。

完成條件：六項都有實際輸出在手，沒有一項靠記憶或推論。

## 第 2 步：找漂移

系統的每個意義都有**單一來源**：門檻在 `chart/anchors.json`、
什麼算對在 `chart/BRIEF.md`、檢查邏輯在 `checks/chart.py`、
流程在 `skills/chart/SKILL.md`、歷史在 `chart/CHANGELOG.md`。
**漂移**＝某個意義偷偷長出第二份。

拿兩份實際文件互相對（不是拿本文件或記憶對），逐項給出「相符／漂移／不適用」，
判為漂移的要指出兩邊差在哪、哪一邊對：

- **檢查程式有沒有真的讀到它宣稱在讀的東西。** 這是 2026-08-21 抓到的那類：
  `chart.series_freshness` 讀 `data`／`points`，而序列的真實欄位是
  `dates`／`values`，於是它對著 13 天封存全綠、一個數字都沒讀到。
  **fixture 也是同一套字典寫的，所以自檢照樣通過。**
  查法是拿一期真資料手算一遍，跟檢查說的比。
- **宣告與事實**：`anchors.publish.static_outputs` 說要產出什麼、
  `System.staged_paths` 說要推什麼、`.git/index` 裡實際有什麼，三者要對得上。
- **同一道門檻，兩側量的是不是同一個東西。** 2026-09-04 抓到的那一類：
  `chart.size` 的 `size_kb` 由 `systems/chart.py` 的 `build()` 量（當時是 compact），
  而 `tools/chart_verify.py` **覆寫**成實際檔案大小。實測差 **1.65 倍**
  （243.5 vs 401.6 KB），那行覆寫的註解卻寫著「差幾個百分點」。
  於是 publish 與預檢對同一期給出兩個答案，`json_fail_kb` 600 這道**發布閘門**
  實際上等於磁碟上的 985 KB。
  **它藏住的方式**：兩邊各自都合理，而**沒有任何一輪會同時看到兩個數字** ——
  執行報告抄 `chart_verify` 的判定，回執只說 publish 有沒有擋。
  查法是拿同一份日檔，把 payload 的 `size_kb` 跟 `chart_verify` 印出來的那個數字並排。
  這一條要對每一個「由 payload 帶進來的量測」問一次
  （`size_kb`、`png`、`prefetch`、`recent_data_paths`），不是只問 size。
- **一個欄位有沒有讀者。** 2026-09-04 抓到的另一類：`series_spec[].t` 的值域
  只活在 `build_series._transform()` 的 if 鏈裡，**沒有任何東西在驗它**，
  而 `build_series.py` 只碰帶 spec 的圖 —— 於是 2026-09-03 那份寫著
  `pct_change_5d`（不存在的轉換）的 spec 安靜地活了一整期。
  查法是問「這個欄位**寫錯的時候，誰會紅**」；答不出來就是沒有讀者，
  而**沒有讀者的欄位不會被違反，只會安靜地變成假的**（同 `anchors.lengths`
  那兩個沒有讀者的數字，見 `_headline_standfirst_was_prose_only`）。
- 篇幅與結構規範：`anchors.lengths` vs `checks/chart.py` 的 `_lengths` vs
  `BRIEF.md` 第四節散文。
- 軌道輪盤（含週末規則）：`anchors.tracks` vs `checks/chart.py` 的 `_track`。
- 15 個 theme 清單：**值域的家是 `kb-core/advisory/anchors.json` 的 `groups`**，
  不是另一份清單。對上游最新一天的實檔比對。
- 五個 slot、theme 不重複、slot 1／2／4 當天性、重製圖 `provenance.inspired_by` 必填。
- 取數限制與代理表：`SOURCES.md` vs `anchors.proxies`／`anchors.rate_limits`。
- **快取有沒有變短。** 2026-08-30 抓到的那一類：來源對最近幾期回空而不是回錯誤碼，
  取數層整檔覆寫，於是快取被砍掉一段而預抓照樣算 `ok`。
  查法是拿一期舊封存畫得出來的序列末日，跟今天 `data/series/*.csv` 的末日比 ——
  **舊期畫得出來、今天畫不出來，就是快取退化了，不是來源今天才壞。**
  守衛在 `fetch.merge_write()`（只能長不能縮），回歸案例 `fetch.py --selftest-cache`。
- **快取的深度是不是我們自己設的、而那個數字有沒有家。** 2026-09-02 抓到的那一類，
  跟上一條是不同的問題：上一條問「有沒有變短」，這一條問「**它從來就是這麼短嗎**」。
  查法是逐檔比各路線的快取跨距——**同一天差距大到量級不同就是有人設了上限**：
  當天台股七條全部 2.00 年，而其他路線 5.22–11.66 年，成因是
  `fetch_tw_price.series()` 的預設 `months=24` 而呼叫端從不覆寫。
  **上限只活在函式預設參數裡就是漂移**：`anchors.history_limits` 是它唯一的家，
  因為那是寫錨點措辭的人唯一會來找的地方。
  順帶要問第二句：**改那個數字補得回歷史嗎？** 台股那次答案是不行
  （增量只從末日往前數），所以另有 `backfill_tw_history.py`。
- QA 旗標分類法與處置：`anchors.quality` vs 近幾期的 `about.qa_dispositions`
  （2026-08-30 更正欄位名，這裡原本寫單數 `qa_disposition`，照它 grep 一筆都找不到）。
- 三大月度數據發布日規則：`anchors.structure.release_day`。
- 圖型選用與多樣性、歷史錨點措辭（`anchors.history_limits`：
  BAML 只有近三年、SOXQ 只回到 2021）。
- **雙軌**：`scripts/chart/chartkit.py` 的 `render_static` 與 `echarts_option`
  是否還同源。四條斷言在 `anchors.rendering.drift_assertions`，
  每一條都是從真實事故反推的。
- 同步組：`skills/chart/SKILL.md` 正本 vs 排程 prompt 副本 vs 本文件，
  結構層面是否一致。
- 排程與實裝：`kb-core/launchd/*.plist` vs `~/Library/LaunchAgents/` 裡的副本
  （對帳指令在 `launchd/README.md`）。

下游那幾格（House View 月報吃的 `charts/<date>/*.png` 與配色、
投顧姊妹庫晨間匯流條吃的 `days[0]`）從網頁上消失＝介面變了，
轉去該系統的 `MAIN.md` 處理，在本 repo 補是補假的。

完成條件：清單每一項都有判定，沒有一項寫「應該沒問題」。

## 排查與稽核（分支）

使用者帶著症狀來 —— 某天沒產出、發布了但網站沒更新、圖上的數字被質疑、
QA 旗標怎麼處置、要做 token 稽核 —— 第 1 步之後接 [`DIAGNOSE.md`](DIAGNOSE.md)，
追出結論再回第 3 步報告。

**「發布了但網站沒更新」有兩種，處置完全不同**：
`data/` 沒上去（推送鏈斷）與 `charts/` 沒上去（宣告漏了）。
回執 `exit 0` 對兩者都會出現，因為它只說到 push 為止 ——
分辨方式是讀 `.git/index` 看哪些路徑真的被追蹤。

## 第 3 步：報告現況，再問要改什麼

報排程狀態、`chart_verify` 結果與旗標處置、theme 與圖型分布、
第 2 步的漂移清單（含哪一邊對）、推送鏈兩側的狀態。

完成條件：使用者看完報告、指定了要改什麼，且你把它覆述成一句話得到確認。
**這一步的產出是報告與那句話，不是任何檔案修改。**

## 第 4 步：執行修改

拿到第 3 步的確認之後，讀 [`MODIFY.md`](MODIFY.md) 並照它走。
