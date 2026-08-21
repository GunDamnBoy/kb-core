# 節目知識庫 · 維護

> **這是正本**，`maintain` 技能裡那份是副本。
>
> **2026-08-21 只做了可查證的更正，這份還沒對著實機完整稽核。**
> 已確認並改掉的：推送者不是 `com.kenny.dashpush`（已退場）、
> 排程 taskId 是 `podcast-daily-300`。
>
> **還沒查證的一件事**：這套系統跟投顧與五圖一樣接上了 kb-core 底盤 ——
> `kb-core/podcast/{BRIEF.md,anchors.json,CHANGELOG.md}` 存在、
> `checks/podcast.py`、`systems/podcast.py`、`tools/podcast_verify.py`、
> `tools/podcast_docx.py` 也都在。所以下面提到的
> `~/podcast-knowledge-digest/AGENT_BRIEF.md` **有可能已經像五圖那份一樣
> 被降級成非權威**（五圖那份掛著失效橫幅、規則搬進了 kb-core）。
> 當時 `~/podcast-knowledge-digest` 沒有掛進工作階段，無從確認。
>
> **下次維護這套時第一件事就是查這個**：`AGENT_BRIEF.md` 開頭有沒有失效橫幅。
> 有的話，本文件與 `FILES.md` 的「規格在 brief」整段都要改成指向 `kb-core/podcast/`。
> **兩份規則同時存在時，改到沒在跑的那一份不會有任何徵兆。**

repo 外的檔案（`podfetch.py`、`config.json`、`shows.json`、排程 `SKILL.md`）**沒有 git**，快照是唯一還原點；排程 `SKILL.md` 還可能在對話進行中被別場維護整份覆寫。動手前重讀當下的檔案，只信這一秒讀到的內容——即使你認為自己就是上一個改它的人。

全程繁體中文（台灣用語）。repo 根目錄 `~/podcast-knowledge-digest`，轉錄管線在 `~/.podfetch/`。

## 硬規矩

- **看檔案狀態用 `cat`／`ls`／`grep`**：`com.kenny.kbpublish.podcast` 每 60 秒跑一次（`~/outbox/podcast/` → `~/podcast-knowledge-digest`），任何 git 指令（含 `git status`）留下的 `.git/index.lock` 都會擋住它。要看推送鏈就 `cat .git/refs/heads/main` 與 `.git/refs/remotes/origin/main` 比對（healthcheck 已經幫你看過）。要實測 git 行為就在 `/tmp` 另建 bare origin ＋ 工作 repo，**不要拿真 repo 試**。
  （**2026-08-21 更正**：上一版寫的是 `com.kenny.dashpush` 每 180 秒 ——
  那支在 2026-08-20 重建時退場，殘骸在 `chart-of-the-day/tools/_to_delete/dashpush-auto-push.sh`。
  九個 launchd 工作裡沒有它。）
- **開工、收工各存一次快照**：`bash ~/.podfetch/snapshot.sh "開工前"`／`"收工後"`。**在 Cowork 沙箱裡跑會缺 `SKILL.md`**（沙箱看不到 `~/Documents/`）——**改過排程 `SKILL.md` 的場次，收工訊息一定要請使用者在 Mac 上補跑一次，並確認那筆快照真的含 `SKILL.md`**。沙箱那份只證明 `.podfetch/` 有備份。
- **Word 報告與 `~/podcast-transcripts` 留在 repo 外**（repo 是 Public）。
- **每個意義各有單一來源**：規格與判斷規則在 `AGENT_BRIEF.md`、流程骨架在排程 `SKILL.md`、事故與來歷在 `MAINTENANCE.md`。寫東西前先決定放哪一份；三份的分工、brief 的篇幅硬限制、以及刻意的雙寫見 [`FILES.md`](FILES.md)。
- **能寫成條件的判斷就寫成條件**——叮嚀會被忽略。
- **`$VAR` 後面緊接全形字元一律加大括號**（shell 腳本）。macOS 的 bash 是 3.2，會把全形括號的高位元組吃進變數名、`set -u` 當場中止；**沙箱是 bash 5.1，測不出來**。改任何只在 Mac 上跑的腳本，都要請使用者在 Mac 實跑一次才算驗收。

每條規矩的來歷與歷史事故在 `MAINTENANCE.md` 第 7 節。

## 第 1 步：載入現況

1. 存開工快照：`bash ~/.podfetch/snapshot.sh "開工前"`。在 Cowork 沙箱裡跑會缺 `SKILL.md`；只能在沙箱裡跑就在報告中請使用者於 Mac 補跑一次。
2. 跑健康檢查——機械式檢查一次做完，並自動把當日指標寫進 `metrics.csv`：

   ```
   python3 ~/.podfetch/healthcheck.py
   ```

   沙箱路徑通常是 `/sessions/<name>/mnt/.podfetch/healthcheck.py`，腳本會自動偵測掛載點。連不到資料夾就用 `mcp__cowork__request_cowork_directory` 連三個資料夾再重跑。FAIL 與 WARN 全部帶進第 3 步的報告。
3. 補**成本基線**的人工欄位：使用者若附了當日 token 分析報告，把**四個數字**抄進 `metrics.csv`——加權總量（千位）→ `eff_tokens_k`、子代理數 → `subagents`、子代理總回合數 → `agent_turns`、**子代理加權總量（千位）→ `subagent_tokens_k`**。這四欄機器量不到（排程執行不在本機留 transcript），**缺任何一欄 `healthcheck.py` 都會出聲**；healthcheck 不會洗掉人工值。每集成本那條曲線全靠這一步累積。
   > **要比效率看 `subagent_tokens_k ÷ transcript_kb`，不要用 `eff_tokens_k ÷ 集數`。** 後者是整場工作階段，混了固定開銷與一次性維護動作，除以集數得到的數字**不可比**——08-15 與 08-17 都踩過這個坑。
4. 讀 `~/podcast-knowledge-digest/MAINTENANCE.md`，尤其第 5 節（新增節目步驟表）、第 7 節（事故檔案）、第 12 節（登記簿）。第 4C 節（podfetch 的四個不要改的設計）只有要動 `podfetch.py` 時才需要讀。第 11 節（變更紀錄歸檔）是純歷史，要查「當初為什麼這樣改」時才回來讀。
5. 讀 `~/podcast-knowledge-digest/AGENT_BRIEF.md` 全文。**它約 24,990 token、`Read` 單次上限約 25,000，餘裕不到 1%**——正常一次讀完，但看到截斷提示就從那一行接著讀完，不要只讀到截斷處。
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
