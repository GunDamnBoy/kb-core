# 節目知識庫 · 維護

> **這是正本**，`maintain` 技能裡那份是副本。
>
> **2026-08-22 已查證，上一版留的那個問題有答案了。**
> 上一版寫「下次維護第一件事就是查 `AGENT_BRIEF.md` 開頭有沒有失效橫幅」——
> **有。** 2026-08-21 標註的橫幅寫著「這份文件只剩一半是權威的」，
> 每一個數字的家已經搬到 `kb-core/podcast/`。本文件與 `FILES.md` 的
> 「規格在 brief」整段已於同日改成指向 kb-core。
>
> **`AGENT_BRIEF.md` 現在仍然權威的只有四塊**（橫幅明文保留）：
> 第 1 節節目清單與全文來源（**A／B 分類與每一檔的官方稿入口只有這裡有**）、
> 第 2 節 podfetch 管線的讀法與排查、第 6 節基礎設施備忘、第 8 節變更紀錄。
> 其餘一律以 `kb-core/podcast/` 為準。
>
> 已確認並改掉的（2026-08-21）：推送者不是 `com.kenny.dashpush`（已退場）、
> 排程 taskId 是 `podcast-daily-300`。

repo 外的檔案（`podfetch.py`、`config.json`、`shows.json`、排程 `SKILL.md`）**沒有 git**，快照是唯一還原點；排程 `SKILL.md` 還可能在對話進行中被別場維護整份覆寫。動手前重讀當下的檔案，只信這一秒讀到的內容——即使你認為自己就是上一個改它的人。

全程繁體中文（台灣用語）。repo 根目錄 `~/podcast-knowledge-digest`。

**轉錄管線住在 `~/kb-core/scripts/podcast/`，不是 `~/.podfetch/`（2026-08-22 實地清點訂正）。**
`podfetch.py`／`healthcheck.py`／`json2docx.py`／`config.json`／`shows.json` 全在 kb-core，
launchd 也是從那裡執行。`~/.podfetch/` 現在只剩**執行期狀態**：
`gemini.key`、`state.json`、`podfetch.log`、`logs/`、`cache/`，
外加兩個指回 kb-core 的 symlink（`config.json`、`shows.json`）與 `metrics.csv`。
**舊文件裡所有 `~/.podfetch/<某支程式>` 的路徑都是過期的**——它們不會報錯，
只會「找不到檔案」，而那跟「這台機器沒裝」看起來一樣。

## 硬規矩

- **看檔案狀態用 `cat`／`ls`／`grep`**：`com.kenny.kbpublish.podcast` 每 60 秒跑一次（`~/outbox/podcast/` → `~/podcast-knowledge-digest`），任何 git 指令（含 `git status`）留下的 `.git/index.lock` 都會擋住它。要看推送鏈就 `cat .git/refs/heads/main` 與 `.git/refs/remotes/origin/main` 比對（healthcheck 已經幫你看過）。要實測 git 行為就在 `/tmp` 另建 bare origin ＋ 工作 repo，**不要拿真 repo 試**。
  （**2026-08-21 更正**：上一版寫的是 `com.kenny.dashpush` 每 180 秒 ——
  那支在 2026-08-20 重建時退場，殘骸在 `chart-of-the-day/tools/_to_delete/dashpush-auto-push.sh`。
  九個 launchd 工作裡沒有它。）
  （**2026-08-24 新增：真的非跑不可時，先確認你刪得掉檔案。** 這條規矩原本只講「會留下
  `.git/index.lock`」，聽起來像「小心一點就好」——不是。**Cowork 掛載點的寫入權限是不對稱的：
  可以建檔，不能刪檔。** 08-24 實測，`git reset --soft` 建了 `.git/HEAD.lock`、
  寫完 HEAD 之後**清不掉自己的鎖**（`unlink: Operation not permitted`），
  於是後面每一個 git 指令都撞 `cannot lock ref 'HEAD': File exists`，
  連 `--no-optional-locks` 也救不了——**你製造了一個自己解不開的死鎖**。
  解法是 `mcp__cowork__allow_cowork_file_delete` 取得該資料夾的刪除權限，再 `rm -f .git/*.lock`。
  **所以順序是：先取得刪除權限，再跑第一個 git 指令**，不要等撞牆才求救。
  唯讀查詢一律加 `--no-optional-locks`，它明確不取機會性的鎖。）
- **不再需要快照（2026-08-22 退役）。** `snapshot.sh` 抄的八個目標裡有七個現在住在 kb-core、有 git，且 `com.kenny.kbcorepush` 每 300 秒自動 commit＋push；唯一在 git 之外的 `~/.podfetch/metrics.csv` 已合併進 kb-core 並改成 symlink。**所以現在沒有任何東西需要快照。** 腳本留著但只會出聲、不建立任何東西——因為**一個照舊印「快照完成」的退役腳本會讓人以為還原點存在**。要還原或看歷史：`cd ~/kb-core && git log -- scripts/podcast/`。
- **Word 報告與 `~/podcast-transcripts` 留在 repo 外**（repo 是 Public）。
- **每個意義各有單一來源**：什麼算對的產出在 `kb-core/podcast/BRIEF.md`、每一個數字在 `kb-core/podcast/anchors.json`、每天怎麼跑在 `kb-core/scripts/podcast/DIGEST-PROMPT.md`、撰寫規則在 `kb-core/scripts/podcast/preamble.md`、節目清單與官方稿入口在 `AGENT_BRIEF.md` 第 1 節、事故與來歷在 `MAINTENANCE.md`。寫東西前先決定放哪一份；完整分工見 [`FILES.md`](FILES.md)。
  **兩份規則同時存在時，改到沒在跑的那一份不會有任何徵兆**——這就是 2026-08-21 到 08-22 之間 brief 被降級卻沒有人改本文件的那個縫。
- **能寫成條件的判斷就寫成條件**——叮嚀會被忽略。
- **`$VAR` 後面緊接全形字元一律加大括號**（shell 腳本）。macOS 的 bash 是 3.2，會把全形括號的高位元組吃進變數名、`set -u` 當場中止；**沙箱是 bash 5.1，測不出來**。改任何只在 Mac 上跑的腳本，都要請使用者在 Mac 實跑一次才算驗收。

每條規矩的來歷與歷史事故在 `MAINTENANCE.md` 第 7 節。

## 第 1 步：載入現況

1. ~~存開工快照~~（2026-08-22 起不必做，理由見上方硬規矩）。改成確認 kb-core 推送鏈是活的：`tail -5 ~/outbox/kbcorepush.log`，看到最近的 `chore(auto)` 或「空輪次」都算正常。
2. 跑健康檢查——機械式檢查一次做完，並自動把當日指標寫進 `metrics.csv`：

   ```
   python3 ~/kb-core/scripts/podcast/healthcheck.py
   ```

   沙箱路徑是 `/sessions/<name>/mnt/kb-core/scripts/podcast/healthcheck.py`，腳本會自動偵測掛載點。連不到資料夾就用 `mcp__cowork__request_cowork_directory` 連四個資料夾再重跑。FAIL 與 WARN 全部帶進第 3 步的報告。

   > **沙箱裡固定會有三則 WARN**（`shows.json 兩份`／`節目在文件裡`／`podfetch`），成因都是 `~/.podfetch` 沒被掛載，不是故障。**但也因此，那三條在沙箱裡等於沒跑**——要真的驗它們得在 Mac 上跑一次。
3. **成本基線那四欄要由「在 Mac 上跑的維護者」補，不是由排程自述**（2026-08-23 訂正）。
   `eff_tokens_k`／`subagents`／`agent_turns`／`subagent_tokens_k` 原本寫「使用者若附了
   當日 token 分析報告就抄進去」，08-22 改成由 `tools/usage_report.py` 讀逐字稿量。
   **方向對，但那支在 Cowork 排程那一側跑不動**：沙箱沒有 `~/.claude/projects`（`exit 14`）、
   `request_cowork_directory` **明文拒絕掛載工作階段儲存區**、
   `session_info__read_transcript` 不回 usage 欄位。三條路 08-23 全部實測過。
   > **但不要把它寫成「排程不留 transcript」** —— 那個結論 08-14 寫過一次、08-16 就被推翻
   > （原因是「五次都是從外面找」），本檔第 6 節與 `healthcheck.py` 的 `measure_session_tokens()` 都記著這件事。
   > **08-23 用 `Glob` 實地確認逐字稿存在**：
   > `~/Library/Application Support/Claude/local-agent-mode-sessions/<帳號>/<工作區>/local_<階段>/.claude/projects/<專案>/<uuid>.jsonl`，
   > 子代理在同層 `<uuid>/subagents/agent-*.jsonl`。
   > **而 `measure_session_tokens()` 裡那段被 early-return 擋掉的程式，glob 樣式正好對得上**
   > （`local-agent-mode-sessions/*/*/*/.claude/projects`，08-23 驗過 `fnmatch` 為 True）。
   > **所以在 Mac 上跑 healthcheck，那四欄是量得到的** —— **但復活它不是拿掉那個 `return` 就好**——它整份掃完會把日報與事後維護算在一起（08-23 實測高估 4.6 倍），要先讓它會切界線。見 `MAINTENANCE.md` 第 6 節。
   > **所以不要「看到空欄就抄回報裡的數字」。** 那是自述不是量測，而
   > `scripts/podcast/metrics-columns.md` 開頭就寫著**用另一套定義填進同一欄比留白更糟**。
   > 實害已經發生：`eff_tokens_k` 08-21＝4913、08-22＝235（自述），而 08-23 實測是 **6,611** —— 當天的自述值是 276，**低估 24 倍**。
   > 08-23 那一列的自述值已在同日抽掉，08-21／08-22 兩列保留不改寫歷史。
   > **量測本身 08-23 已經成功**（在 Mac 上跑 `usage_report.py`，日報那一輪 6,611K），結果寫進 `kb-core/metrics/usage.csv`；`metrics.csv` 那四欄維持留空。
   > **`healthcheck.py` 的那則「每日指標」WARN 已於 08-23 改寫**，不再催人去填、改成說明為什麼留空。
   > **注意它在沙箱裡整條不會出現**（`metrics()` 寫 `~/.podfetch/`，沒掛載就整個 except 掉，
   > 輸出裡連「每日指標」四個字都沒有）—— 08-23 就是這樣才發現本節上一版寫的
   > 「缺欄會出聲」在沙箱裡沒被驗證過。**要驗這一則得在 Mac 上跑。**
   > **真要比效率看 `subagent_tokens_k ÷ transcript_kb`，不要用 `eff_tokens_k ÷ 集數`** ——
   > 後者混了固定開銷與一次性維護動作，除以集數不可比（08-15、08-17 都踩過）。
4. 讀 `~/podcast-knowledge-digest/MAINTENANCE.md`，尤其第 5 節（新增節目步驟表）、第 7 節（事故檔案）、第 12 節（登記簿）。第 4C 節（podfetch 的四個不要改的設計）只有要動 `podfetch.py` 時才需要讀。第 11 節（變更紀錄歸檔）是純歷史，要查「當初為什麼這樣改」時才回來讀。
5. 讀規格。**現在是四份小的，不是一份大的**：`kb-core/podcast/BRIEF.md`、`kb-core/podcast/anchors.json`、`kb-core/scripts/podcast/DIGEST-PROMPT.md`、`kb-core/scripts/podcast/preamble.md`。要動節目清單、官方稿入口或 podfetch 內部時，另外讀 `~/podcast-knowledge-digest/AGENT_BRIEF.md` 的第 1／2／6 節。
   > **那條「brief 約 24,990 token、餘裕不到 1%」的警告已經不再是每日的硬限制**（2026-08-22）——每日排程不再完整讀 `AGENT_BRIEF.md`，它只在需要 A 類清單時讀第 1 節。**但拆檔之後多了一個新的失效形態**：四份小的各自都很好讀，於是很容易只改其中一份。查漂移時四份要一起看。
6. `mcp__scheduled-tasks__list_scheduled_tasks` 記下 `cronExpression`／`enabled`／`nextRunAt`／`lastRunAt`，並 Read 它回傳的 `path` 全文。
7. 讀 `~/podcast-knowledge-digest/data/index.json`。

完成條件：七項都有實際輸出在手，沒有一項靠記憶或推論。健康檢查已涵蓋的項目到此為止，注意力留給腳本抓不到的東西——也就是下一步。

## 第 2 步：找漂移

`healthcheck.py` 抓得到的是**機械式**與數值型的不一致；歷史上出問題的幾乎都是**敘述性**的，只能靠讀。敘述性比對**固定外包給 Agent 子代理**：主線自認「大體同步」的場次，子代理照樣成串抓出矛盾——覆寫事故、會讓新架構直接失效的跨檔案系統假設、主線當天自己寫出的錯誤因果，以及已經記過的同型錯誤又犯一次。

把 [`SYNC-CHECKLIST.md`](SYNC-CHECKLIST.md) 整份交給子代理當任務指示（讓它讀這份檔，或逐字貼進指示）。

完成條件：清單每一區都有結論（相符／不一致／不適用），不一致處逐處帶行號與原文。回報「大體同步」而點不出具名條目＝沒做完，重派。

## 第 3 步：報告現況，再問要改什麼

報健康檢查結果（FAIL 與 WARN 逐條列出，PASS 一行帶過）、排程狀態與最近幾天集數（0 集日不產檔是正常的）、第 2 步的漂移清單（具體指出哪幾處，含 brief 內部自打架）、`MAINTENANCE.md` 第 6 節的待辦與觀察中事項。

完成條件：使用者看完報告、指定了要改什麼，且你把它覆述成一句話得到確認。這一步的產出是報告與那句話，不是任何檔案修改。

## 第 4 步：執行修改

拿到第 3 步的確認之後，讀 [`MODIFY.md`](MODIFY.md) 並照它走——改哪個檔、排程 `SKILL.md` 整份覆寫的規矩、brief 第 8 節歸檔、第 12 節登記簿、節目清單異動的連鎖點，以及改完必須全數通過的驗證清單。

> **一輪只改一小批，每一批各自收尾。** 一場裡連改多批時，「記錄本場」這件事本身會落後於改動——**量測與登記要排在每一批的收尾，不是整場的收尾**，否則寫進登記簿的數字會停在中途值，而且後面幾批很容易完全漏掉登記。

## 排查

某日沒產出、集數缺漏、podfetch 疑似失效、或某個值疑似今天被人動過——第 1 步跑完就讀 [`DEBUG.md`](DEBUG.md)，不必等到第 4 步。
