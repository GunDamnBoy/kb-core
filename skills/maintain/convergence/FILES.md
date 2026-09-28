# 文件分工與系統形狀

第 1／2 步查漂移時對照用。標**唯一正本**的地方沒有副本——任何看起來像副本的東西就是漂移。

| 檔案 | 只放什麼 | 誰讀 |
|---|---|---|
| `convergence-weekly/AGENT_BRIEF.md` | 現在的規格與判斷規則、單期 JSON schema、上游庫清單與計票規則（第 0 節）、**「一組要一起改」清單的唯一正本**（第 3.0 節末） | 每週排程完整讀一次 |
| `kb-core/skills/convergence/SKILL.md` | 排程 prompt 的**正本**：流程骨架、環境自檢、exit 表 | 排程執行時（桌面排程裡是它的副本，本文逐字相同） |
| `convergence-weekly/MAINTENANCE.md` | 維護流程、排程位置與 cron、已知的坑、待辦、事故與決策檔案 | 維護者 |
| `convergence-weekly/CHANGELOG.md` | 逐版變更、度量趨勢、失效模式目錄、回溯要點 | 維護者 |
| `kb-core/systems/convergence.py` | payload 組法、index 快照、errata-only 守衛、**帳本折入 `fold_calls` 與指紋基準** | 實作 |
| `kb-core/checks/convergence.py` | 閘門的全部檢查（唯一正本） | 實作 |

新的事實細節寫 brief；新的「為什麼」寫 MAINTENANCE 或 CHANGELOG。**執行視野**只有 brief 與 prompt 兩份——要生效的規則就得落在這兩份裡。

資料檔（全部由 kb-core publish 寫）：`data/index.json`（封存索引、量化快照、errata）、`data/calls.json`（訊號帳本）、`data/upstream.json`（上游指紋基準，只在發布最新一期時更新）。`data/YYYY-MM-DD.json` 是每期封存，只讀不改。

## 系統形狀

五個獨立知識庫（投顧、節目、AI 泡沫監控、每日五圖、外資報告週摘）互相看不到對方，疊起來才看得到四種訊號：**三方共振**（三個獨立聲音；投顧＋圖表算一票）、**關鍵背離**（核心價值）、**共識裂縫**（掛在 item 上的 tag，不是章節）、**單邊訊號**（只標記不判斷）。v2 起另有**賣方對帳**節，裁決 `stances.json` 裡到期的分析師主張並寫回。

兩個跨期累積機制：**訊號帳本**（可證偽判斷登帳 → publish 折入 → 下期 PREP 逼驗收 → 站台記分板）與**上游改版偵測**（監控庫指紋 diff，開工前在 `PREP.md` 頂部亮 🛑）。**兩者都靠 publish 每期寫檔**——2026-08-23～09-28 那一段沒人寫，兩個機制都靜默失效（CHANGELOG 3.5）。

排程 taskId `convergence-weekly-1500`，每週一台北 15:00，Cowork 桌面夾四個資料夾（`convergence-weekly`／`outbox`／`kb-core`／`broker-research-digest`）。草稿寫 `~/outbox/convergence/`，由 launchd `com.kenny.kbpublish.convergence` 每 60 秒發布、寫回執。

## 上游介面

**系統 id ≠ repo 路徑。** 投顧的系統 id 是 `advisory-knowledge-hub`，現役 repo 是 `advisory-rewrite`；同名舊 repo 8/18 起停更，clone 它**不報錯、只會安靜地拿到零天**。`prepare.py` 的 `REPOS` 是唯一的來源清單。

投顧庫的每日 JSON 與其 `data/index.json` 各日 entry 帶機器可讀欄位，**跨庫比對可以直接吃**：卡片 `thread`（跨日主題連續劇代號）、`overview.pulse`（五資產每日立場）、`overview.watchReview`（上游自己的盯盤驗證戰績，可與本系統帳本互驗）、`thermo` 數值日序列與 `snap` 數值鏡像。正本規格在投顧 repo 的 brief，本檔只記「它們存在」。是否納入計票規則由當期維護決定，並寫進本系統 brief 第 0 節。
