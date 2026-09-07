---
name: maintain
description: 七套自動化系統的維護入口——投顧知識庫儀表板、每日五圖、Podcast 摘譯、外資報告週摘、AI 泡沫監控、主題匯流訊號報、Houseview 月報。改規格／來源／版面／排程、排查某期沒產出或異常、查跨版趨勢或做稽核時觸發。外資報告、券商報告、原句牆、立場帳本、精華、標籤也走這裡。
---

# 七套系統的維護入口

先認出是哪一套，再照那一套的 `MAIN.md` 走。**認錯系統會改到別人的 repo**，所以這一步先做完再開口。

| 系統 | 資料夾 | 排程 taskId | 資料 repo | 認得出來的字 |
|---|---|---|---|---|
| 投顧知識庫儀表板 | `advisory/` | `advisory-daily-0730` | `~/advisory-rewrite` | 新聞來源、子類別、分級下限、徽章、跨版趨勢 |
| 每日五圖 | `chart/` | `chart-daily-1130` | `~/chart-of-the-day` | slot、軌道輪盤、圖型、chartkit、token 稽核 |
| Podcast 摘譯 | `podcast/` | `podcast-daily-300` | `~/podcast-knowledge-digest` | 節目清單、`podfetch`、轉錄、集數缺漏、成本基線 |
| 外資報告週摘 | `research/` | 「外資報告週摘（週日深夜）」 | `~/broker-research-digest` | 外資／券商報告、精華、原句牆、立場帳本、標籤、浮水印、重製圖 |
| AI 泡沫監控 | `bubble/` | `bubble-weekly-0900`（每週一） | — | 指標、層權重、計分錨點、觸發器、台股子模型 |
| 主題匯流訊號報 | `convergence/` | `convergence-weekly-1500`（每週一） | `~/outbox/convergence/` → `com.kenny.kbpublish.convergence` | 每週、跨庫、訊號帳本、發布閘門、上游改版偵測 |
| 國際市場 Houseview 月報 | `houseview/` | `houseview-weekly-1630`（每週五） | — | 月度 pptx、十五章、縱深、DROPPED、版面壓字 |

**前四套是活的**（2026-08-22 查證：排程與 launchd 都在跑，且都接上了
`~/kb-core` 的共用底盤 —— 門檻在 `kb-core/<系統>/anchors.json`、
檢查在 `kb-core/checks/<系統>.py`、發布走 `kb-core/tools/publish.py`）。
**外資報告週摘是其中唯一週頻的**：它的哨兵門檻、不可改寫規則都跟前三套不同，
照日頻那三套的直覺去判會判錯。

**後三套現在也都有排程，而且都在跑** —— 2026-09-03 用 `list_scheduled_tasks` 查證：
`bubble-weekly-0900`（enabled，每週一，lastRun 2026-08-31）、
`convergence-weekly-1500`（enabled，每週一，lastRun 2026-08-31，草稿寫進
`~/outbox/convergence/` 由 `com.kenny.kbpublish.convergence` 發布）、
`houseview-weekly-1630`（enabled，每週五，lastRun 2026-08-28）。
**但這三套的文件仍停在 2026-08-20 重建之前，所以「排程在跑」不等於「文件可信」。**
碰它們之前先跟使用者確認現況，**不要照那三份文件的路徑直接動手**。

> ~~後三套在這台機器上沒有排程也沒有 launchd 工作，待重建。~~
> **2026-09-03 更正。** 這句話至少從 2026-08-24（`convergency-weekly-2100` 被
> `convergence-weekly-1500` 取代那天）起就已經不成立了。
> **它錯的方向特別糟**：它叫維護者把三套當成死的，而它們每週在跑、其中一套還會發布 ——
> 「以為它沒在跑」比「以為它在跑」更危險，因為前者不會有人去看它的產出。

**`advisory-knowledge-hub`／`chart-of-the-day`／`podcast-knowledge-digest`
是系統 id，不一定等於路徑。** 投顧就是這樣踩到的：同名的舊 checkout
`~/advisory-knowledge-hub` 停在 2026-08-18，**讀它不會報錯、只會安靜拿到舊資料** —— 已於 2026-08-21 搬到 `~/_to_delete/advisory-knowledge-hub-stale-20260818`，所以現在走錯會直接找不到檔案。**路徑一律看上表那一欄。**

認出來就 Read `<資料夾>/MAIN.md`，之後整場照它走。它會指向同資料夾內的其他 `.md`（`FILES.md`、`MODIFY.md`、各系統另有的診斷或比對檔），**一律在同一個資料夾裡找**。

完成條件：是哪一套已經確定，且該資料夾的 `MAIN.md` 已完整讀過。使用者的話同時指向兩套以上（例如「匯流條掛了」牽涉三套），先問他要從哪一套進去。

## 「那一輪有沒有跑」不要問排程器（2026-09-07）

**桌面排程器的自述欄位都不能當證據。** 那天的實測：

| 時刻（台北） | 量到的事 |
|---|---|
| 11:30 | `chart-daily-1130` 觸發 |
| 11:59 | `~/outbox/chart/2026-09-07.receipt.json`　`exit 0`　commit `676da60` |
| 12:00 | `~/outbox/chart/2026-09-07-run-report.md` |
| 13:2x | `list_scheduled_tasks` 的 `lastRunAt` **仍是 `2026-09-06T03:31:18Z`** |

**一輪確實跑完、發布成功、留下回執與報告，而 `lastRunAt` 沒有動。**
同一天也量到 `nextRunAt` 是**派工當下**就往前推進的，不是跑完才推 ——
所以「`nextRunAt` 跳過去了」既不代表跑完，也不代表被丟掉。

**那天靠這兩個欄位下的診斷錯了兩次**：先把「還在跑」的 chart 讀成「沒有來」，
再從「`nextRunAt` 往前跳」推出「排程被靜默丟棄」。
兩次都是同一個形狀 —— **拿一個近似的觀測當成結論**。

**唯一可信的是產出檔**：`~/outbox/<目錄>/<日期>.receipt.json`（advisory 在 outbox 根目錄）。
用產出檔重掃，那天真正的樣子是 podcast ✅、advisory ❌、bubble ❌、chart ✅ ——
**不是一段時間窗口，是特定兩支沒跑，而它前面那支和後面那支都跑了。根因當時未定。**

### 哨兵：`tools/schedule_gaps.py`

`com.kenny.kbschedgaps` 每天 **13:10** 跑，只讀產出檔，寫 `~/.kbusage/schedule-gaps.md`。
**它跑在 launchd 上，不是桌面排程器上** —— 那天 launchd 全綠而桌面排程器漏了兩支，
**哨兵掛在被監視的對象上就會跟著一起安靜**。

它補的是 `com.kenny.kbgaps` 上面那一層：`usage_gaps.py` 拿回執在不在當成「那天跑了」，
所以**輪次根本沒被觸發時它回 0、一聲都不會出**。

**⚠️ 改任何一套的排程時間或星期，要一起改 `schedule_gaps.py` 的 `SCHEDULE`。**
那張表是排程器 cron 的第二份拷貝 —— 這個 repo 別處禁止第二份拷貝，這裡破例，
理由就是上一段。**代價是它會漂，而漂了不會有東西叫**，所以只能寫進這裡靠人記得。
停用一支排程時也要把它從 `SCHEDULE` 拿掉，否則它會天天誤報，**而誤報一次就沒有人看了**。

## 跨系統接手

這七套互相吃對方的產出。追到問題出在上游時，**直接轉去那一套的 `MAIN.md` 接著查**——同一支 skill 之內換個資料夾而已，不必回頭問。轉過去之後照新那套的步驟走，最後的報告寫清楚你跨了哪幾套、各自的結論是什麼。

**動到第二個 repo 的檔案之前先停下來確認**：診斷可以跨，修改要問過。各系統的 `MAIN.md` 第 3 步本來就有這道關卡，跨過來一樣要過。

## 這份文件的正本

正本在 **`~/kb-core/skills/maintain/`**，跟程式一起進版控；技能裡這一份是副本。

改維護文件的流程是：改 kb-core 正本 → 把整個 `maintain` 目錄打包成 `.skill`
→ 安裝覆蓋。**技能的子檔沒辦法從工作階段直接更新** ——
`save_skill` 只取代 `SKILL.md`，其餘檔案原樣保留，
而快取是唯讀的，改它不會保存。
