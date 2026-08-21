---
name: maintain
description: 六套自動化系統的維護入口——投顧知識庫儀表板、每日五圖、Podcast 摘譯、AI 泡沫監控、主題匯流訊號報、Houseview 月報。改規格／來源／版面／排程、排查某期沒產出或異常、查跨版趨勢或做稽核時觸發。
---

# 六套系統的維護入口

先認出是哪一套，再照那一套的 `MAIN.md` 走。**認錯系統會改到別人的 repo**，所以這一步先做完再開口。

| 系統 | 資料夾 | 排程 taskId | 資料 repo | 認得出來的字 |
|---|---|---|---|---|
| 投顧知識庫儀表板 | `advisory/` | `advisory-daily-0730` | `~/advisory-rewrite` | 新聞來源、子類別、分級下限、徽章、跨版趨勢 |
| 每日五圖 | `chart/` | `chart-daily-1130` | `~/chart-of-the-day` | slot、軌道輪盤、圖型、chartkit、token 稽核 |
| Podcast 摘譯 | `podcast/` | `podcast-daily-300` | `~/podcast-knowledge-digest` | 節目清單、`podfetch`、轉錄、集數缺漏、成本基線 |
| AI 泡沫監控 | `bubble/` | **本機無排程** | — | 指標、層權重、計分錨點、觸發器、台股子模型 |
| 主題匯流訊號報 | `convergence/` | **本機無排程** | — | 每週、跨庫、訊號帳本、發布閘門、上游改版偵測 |
| 國際市場 Houseview 月報 | `houseview/` | **本機無排程** | — | 月度 pptx、十五章、縱深、DROPPED、版面壓字 |

**前三套是活的**（2026-08-21 查證：排程與 launchd 都在跑，且都接上了
`~/kb-core` 的共用底盤 —— 門檻在 `kb-core/<系統>/anchors.json`、
檢查在 `kb-core/checks/<系統>.py`、發布走 `kb-core/tools/publish.py`）。

**後三套在這台機器上沒有排程也沒有 launchd 工作**，文件停在 2026-08-20 重建之前，
待重建。碰它們之前先跟使用者確認現況，**不要照那三份文件的路徑直接動手**。

**`advisory-knowledge-hub`／`chart-of-the-day`／`podcast-knowledge-digest`
是系統 id，不一定等於路徑。** 投顧就是這樣踩到的：同名的舊 checkout
`~/advisory-knowledge-hub` 還在硬碟上、停在 2026-08-18，
**讀它不會報錯、只會安靜拿到舊資料**。路徑一律看上表那一欄。

認出來就 Read `<資料夾>/MAIN.md`，之後整場照它走。它會指向同資料夾內的其他 `.md`（`FILES.md`、`MODIFY.md`、各系統另有的診斷或比對檔），**一律在同一個資料夾裡找**。

完成條件：是哪一套已經確定，且該資料夾的 `MAIN.md` 已完整讀過。使用者的話同時指向兩套以上（例如「匯流條掛了」牽涉三套），先問他要從哪一套進去。

## 跨系統接手

這六套互相吃對方的產出。追到問題出在上游時，**直接轉去那一套的 `MAIN.md` 接著查**——同一支 skill 之內換個資料夾而已，不必回頭問。轉過去之後照新那套的步驟走，最後的報告寫清楚你跨了哪幾套、各自的結論是什麼。

**動到第二個 repo 的檔案之前先停下來確認**：診斷可以跨，修改要問過。各系統的 `MAIN.md` 第 3 步本來就有這道關卡，跨過來一樣要過。

## 這份文件的正本

正本在 **`~/kb-core/skills/maintain/`**，跟程式一起進版控；技能裡這一份是副本。

改維護文件的流程是：改 kb-core 正本 → 把整個 `maintain` 目錄打包成 `.skill`
→ 安裝覆蓋。**技能的子檔沒辦法從工作階段直接更新** ——
`save_skill` 只取代 `SKILL.md`，其餘檔案原樣保留，
而快取是唯讀的，改它不會保存。
