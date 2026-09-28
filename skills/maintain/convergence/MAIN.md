# 主題匯流訊號報 · 維護

它不產出資訊，它產出**訊號的合成**：五個互相看不到對方的上游知識庫，疊起來才看得到的東西。一期讀起來像「本週新聞回顧」就是失敗。訊號種類、跨期機制、文件分工與上游介面見 [`FILES.md`](FILES.md)。

全程繁體中文（台灣用語）。資料 repo 在本機 `~/convergence-weekly`（沙箱掛載點用 `ls -d /sessions/*/mnt/*/` 找；讀不到就用 `request_cowork_directory` 連），站台 <https://gundamnboy.github.io/convergence-weekly/>。發布、閘門、帳本折入都在 **`~/kb-core`**——維護這一套通常要同時夾這兩個資料夾，外加 `~/outbox` 與 `~/broker-research-digest`。

> 本檔 2026-09-29（v2.1）對齊 v2。在那之前它還在寫 dashpush、repo 內的 `publish.py`／`healthcheck.py`、週日晚間——**照舊版做會跑到已退場的腳本**。

## 正本與複本

系統的每個意義都有**正本**，本檔不持有會隨版本**漂移**的值——來源清單與數量、字數門檻、章節數、cron 字串、檔案清單、檢查項目明細，一律以 repo 內文件為正本。本檔只放三件事：讀哪些正本、怎麼比對、哪些不變式不能鬆。本檔與 repo 文件矛盾時**以 repo 文件為準**，並在收工時改 `~/kb-core/skills/maintain/convergence/` 正本、整個 `maintain` 目錄重新打包成 `.skill` 請使用者安裝（`save_skill` 只取代 `SKILL.md`，快取唯讀）。

## 硬規矩

- **沙箱裡不要對本機 repo 跑任何 git 指令**（含 `git status`）：掛載檔案系統不支援 git 的 lock 語意，留下的 `.git/index.lock` 會擋住 kb-core publish。看狀態用 `cat`／`ls`／`grep`，或在 `/tmp` 另 clone 一份 GitHub 版本做 `diff -rq --exclude=.git --exclude=work`。
- **發布只走 kb-core 的 `tools/publish.py`**：草稿寫 `~/outbox/convergence/<日期>.draft.json`，launchd `com.kenny.kbpublish.convergence` 每 60 秒接手、寫回執。**不要直接寫 `data/<日期>.json`**，那是繞過閘門。outbox 裡的草稿一分鐘內就會被發布、而且刪不掉——**先在別處組好、`convergence_verify.py` 驗過才放進去**。
- **`data/YYYY-MM-DD.json` 只讀不改**：發布後才發現的問題走 `errata`。最新一期走發布軌（草稿加 `errata`、其餘一字不動）；**舊期直接寫 `data/index.json` 該期 entry**（閘門會拿今天的語料重驗舊期，必然 FAIL）。
- **publish 只 commit `data/`**。改了 `prepare.py`、brief、MAINTENANCE 等**已追蹤的非 data 檔**，收工時必須請使用者手動 `git add … && git commit && git push`——否則下一次發布回 exit 15 @ worktree-dirty，而排程 clone 到的還是舊版。交付訊息要列出確切的檔名與指令。
- **cron 以台北本地時間寫**（不是 UTC）；正確值以 `list_scheduled_tasks` 為準，`MAINTENANCE.md` 第 3 節記同一份。
- **訊號稀薄的一期就照實寫**：真沒有背離就寫「本週五庫高度一致，這本身是訊號」，章節據實留白。

每條規矩的來歷與其他歷史坑在 `MAINTENANCE.md` 第 4、6 節，重複踩過的失效模式在 `CHANGELOG.md` 第 3 節。

## 第 1 步：載入現況

1. **取一份乾淨的對照**：`git clone --depth 1 https://github.com/GunDamnBoy/convergence-weekly.git /tmp/cwgh`，跟本機 `diff -rq`。有差異＝有人改了沒提交（下次發布會 exit 15），先帶進報告。
2. 讀 `AGENT_BRIEF.md` 全文、`MAINTENANCE.md` 全文、`CHANGELOG.md` 最新一版＋版本索引。
3. 用 `list_scheduled_tasks` 找 `convergence-weekly-1500`，記 cron／enabled／nextRunAt／lastRunAt，並讀 prompt 全文（`path` 欄位；讀不到時用 uploads 裡的副本），對照正本 `kb-core/skills/convergence/SKILL.md`。**lastRunAt 不是「那一輪有沒有跑」的證據**——看 `~/outbox/convergence/<日期>.receipt.json`。
4. 讀 `data/index.json`（最近三期與量化快照、errata）、`data/calls.json`（戰績與未結案帳目——**它應該在每期發布後更新**，mtime 停住就是折帳壞了）、`data/upstream.json`（同理）。
5. 讀最近兩期的回執與 `publish.log` 尾巴。
6. 需要驗內容時：在 `/tmp` 跑一次 `prepare.py`（`--work` 指容器本地），再對最新一期跑 `kb-core/tools/convergence_verify.py`。**`healthcheck.py` 已退場，不要跑。**

完成條件：六項都有實際輸出在手，沒有一項靠記憶或推論。

## 第 2 步：找漂移

機械檢查抓不到敘述性矛盾，只能靠讀。**固定用 Agent 子代理獨立比對**——歷次維護的子代理複查命中率 100%（CHANGELOG 3.3 有統計）。給子代理的要求：指出行號與原文、只回報不一致處、指明哪一邊是對的，回報就是產出。

**漂移**＝某個意義偷偷長出第二份，或兩份正本各說各話。逐面向查，每面向給出「相符／漂移／不適用」；判為漂移的要指出兩邊差在哪、哪一邊是對的。事實基準是**實作**（kb-core `systems/`、`checks/`、`tools/publish.py`）與現行排程。

**排程 prompt ↔ 正本 ↔ brief ↔ 實作**

- 排程裡的 prompt 與 `kb-core/skills/convergence/SKILL.md` 本文是否逐字一致
- 流程步驟與分支判斷（環境自檢、來源 grep、不產期、樣本偏薄、上游改版 🛑、帳本結案、賣方對帳）
- 發布路徑：outbox → kb-core publish → 回執、exit 表的語意
- calls 登帳準則（id 格式、claim＋judge 必填、result 值域、改判擋下、同結果重判 no-op、void 的定位）
- 交付訊息的行數與內容
- 規則有沒有落在**執行視野**內：每週排程讀得到的只有 brief 與 prompt，規則寫在 CHANGELOG 或 MAINTENANCE 等於沒生效（CHANGELOG 3.2，已發生三次）

**四條正確性不變式（每一份文件裡都維持原狀）**——它們看起來像效率或風格問題，實際上都是正確性問題：

- 兩個敘事子代理**平行且互相看不到對方**（一鬆，「共振」就變自我實現的預言）
- 合成順序**先量化後敘事**（反了就找不到背離）
- 量化佐證只取 `events` **以外**的來源（events 是 Google News，與各庫**同源**，同一則新聞會被數兩次）
- **投顧與圖表計為同一票**（圖表庫選題與投顧**同源**）；券商是獨立的第四票，但共振門檻仍是三方

**上游路徑**：`prepare.py` 的 `REPOS` 每一個 URL 是否仍是該系統**現役**的資料 repo（系統 id ≠ repo：投顧是 `advisory-rewrite`）。對每一庫確認 clone 下來的最新日期接近今天。

**brief 內部自我一致性**：數值打架、上文被下文取代沒改、待決事項已解決沒劃掉、schema 與實作是否同步。「一組要一起改」的清單以 brief 第 3.0 節末為**唯一正本**。

**兩份成對的函式**：`cwlib.upstream_fingerprint`（prepare 讀基準）與 kb-core `systems/convergence.upstream_fingerprint`（publish 寫基準）必須逐欄相同。

完成條件：每個面向都有判定，判為漂移的都附行號與原文；四條不變式在 brief 與 prompt 兩份裡逐條確認過。

## 第 3 步：報告現況，再問要改什麼

報：排程狀態、最近三期與跨期趨勢點數、**帳本戰績**（讀 `calls.json`）、上游路徑是否現役、第 2 步的漂移清單（具體指出哪邊對）、MAINTENANCE 的待辦、本機與 GitHub 的差異。

完成條件：使用者看完報告、指定了要改什麼，且你把它覆述成一句話得到確認（使用者已明示授權執行者時，覆述的對象是那份授權）。這一步的產出是報告與那句話，不是任何檔案修改。

## 第 4 步：執行修改

拿到第 3 步的確認之後，讀 [`MODIFY.md`](MODIFY.md) 並照它走——改哪個檔、schema「一組一起改」、排程 prompt 整份取代與兩處同輪同步、新增比對來源的第一個問題、發布軌的順序限制、CHANGELOG 該寫的四項，以及改完必須全數通過的驗證清單。
