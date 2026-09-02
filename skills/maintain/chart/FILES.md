# 檔案地圖、同步組與系統形狀

> **這是正本**，`maintain` 技能裡那份是副本。
> 上一版的檔案地圖整張停在 2026-08-20 重建之前：`AGENT_BRIEF.md` 與
> `tools/check_day.py` 都已不是權威（前者掛著失效橫幅、後者退休到
> `chart-of-the-day/tools/_to_delete/`）。

第 2 步查漂移時對照用。標**唯一權威版本**的檔案沒有副本 ——
任何看起來像副本的東西就是漂移。

## 兩個 repo 的分工

| | 路徑 | 放什麼 |
|---|---|---|
| 程式與規格 | `/Users/macmini/kb-core` | 門檻、檢查、程式、流程正本、維護文件正本 |
| 已發布的資料 | `/Users/macmini/chart-of-the-day` | `data/`、`charts/`、`index.html` |

**資料 repo 只放已發布的東西。** 門檻是程式的一部分，放進資料 repo 會讓
「改門檻」跟「改資料」混在同一個歷史裡。

## 同步組是三份，不是兩份

| 這一份 | 怎麼更新 |
|---|---|
| 流程正本 `kb-core/skills/chart/SKILL.md` | 直接編輯 |
| 排程 prompt（taskId `chart-daily-1130`） | `mcp__scheduled-tasks__update_scheduled_task`，**整份取代**；先改正本再整份貼過去 |
| 維護文件正本 `kb-core/skills/maintain/chart/*.md` | 直接編輯，然後**整包重打 `maintain.skill` 安裝** |

**技能的子檔沒辦法從工作階段更新**：`save_skill` 只取代 `SKILL.md`，
其餘檔案原樣保留。所以流程是「改 kb-core 正本 → 把整個 maintain 目錄
（含未改動的另外五套）打包成 `.skill` → 安裝覆蓋」。
直接改唯讀快取不會保存。

改動涉及結構（節號、檔案位置、機制增減）時，三份都要動。

## 檔案地圖

路徑相對於 `/Users/macmini/kb-core`，除非另有標明。

| 檔案 | 角色 |
|---|---|
| `chart/anchors.json` | **每一個數字的唯一的家**。門檻、篇幅、輪盤、配色、代理表、限流、歷史深度 |
| `chart/BRIEF.md` | 什麼算對的產出。有數字就指路到 anchors，不抄值 |
| `chart/SOURCES.md` | 取數眉角與可用來源。第 3 步才需要，靠指標到達 |
| `chart/CHANGELOG.md` | 歷版變更紀錄，五欄結構，最新一筆在最上面 |
| `skills/chart/SKILL.md` | 每天怎麼跑的**流程正本** |
| `scripts/chart/RUN-PROMPT.md` | 排程 prompt 的正本 |
| `checks/chart.py` | 十八條檢查。**數字一律從 anchors 讀**，這裡是它的讀者不是第二份副本 |
| `systems/chart.py` | payload 怎麼組、index entry、`staged_paths`（要推哪些路徑） |
| `kbcore/system.py` | `System` 登記的形狀 —— 新增維度先加在這裡 |
| `tools/chart_verify.py` | 驗一天，**不發布、無副作用**。回測舊期用它 |
| `tools/publish.py` | 唯一的發布路徑，**三套系統共用** |
| `tools/push_kbcore.py` | 推 kb-core 自己，帶靜置與自檢閘門 |
| `scripts/chart/chartkit.py` | 雙軌繪圖實作（`render_static` ＋ `echarts_option`） |
| `scripts/chart/build_series.py` | 序列轉換 `_transform` 的**唯一實作**（月頻按日曆回推、不按位置） |
| `scripts/chart/render_day.py` | 當期渲染；`to_chart` 的欄位自動帶入在這裡 |
| `scripts/chart/rebuild_option.py` | **修舊期渲染缺陷的唯一合法工具**（`--png` 可重繪） |
| `scripts/chart/prefetch.py` | 11:00 的序列預抓；`--history <id>` 離線讀末日歷史 |
| `scripts/chart/scan_moves.py` | slot 2 的異動掃描；只讀快取、不連外。**分位樣本逐列標示**，★＝該列快取短於 `--years` 要求 |
| `scripts/chart/backfill_tw_history.py` | **一次性**把台股快取補到 `history_limits.tw_route_months`；強制全量、預設一次兩條。**改預設月數不會補到歷史，只有這支會** |
| `scripts/chart/macro_release.py` | 三大月度數據的發布偵測 |
| `launchd/` | 九個 plist 的版控副本 ＋ README（實裝在 `~/Library/LaunchAgents/`） |
| `chart-of-the-day/data/<日期>.json` | 每日封存（含完整 `series`），**只讀** |
| `chart-of-the-day/data/index.json` | 封存索引；`days[0]` 被姊妹庫讀 |
| `chart-of-the-day/data/series/*.csv` | 序列快取，檔頭記來源與抓取日期 |
| `chart-of-the-day/data/_prefetch_status.json` | 最近一輪預抓的狀態，**每天被覆寫**（`chart.prefetch_fresh` 讀它） |
| `chart-of-the-day/data/_prefetch_history.jsonl` | 每輪一行的末日歷史（2026-09-01 起）。**append-only、沒有檢查在讀**，用來判某條序列的發布節奏——`anchors.freshness.release_cadence_ledger` |
| `chart-of-the-day/charts/<日期>/` | PNG（200dpi）與 SVG，**對外契約** |
| `chart-of-the-day/index.html` | 前端，動態渲染：加 theme 不用改，改欄位名才要動 |

### 已失效但還留著的

| 檔案 | 狀態 |
|---|---|
| `chart-of-the-day/AGENT_BRIEF.md` | 掛著「2026-08-20 起不再是權威」橫幅。**讀它可以，照它做不行** |
| `chart-of-the-day/MAINTENANCE.md` | 同上；還沒刪是因為有事故紀錄沒搬完 |
| `chart-of-the-day/tools/_to_delete/` | `check_day.py`、舊 `chartkit.py`、`dashpush-auto-push.sh` 等殘骸 |

**兩份規則同時存在時，改到沒在跑的那一份不會有任何徵兆。**

## 系統形狀

改這幾件事之前先跟使用者確認（走第 3 步）。

- 每天五張自製圖 ＋ 判讀，封存成獨立 JSON（含完整 `series`），任何一天都能原樣重畫。
- **五張、slot 順序、theme 不重複、軌道對星期** —— 這四件是系統的定義，
  不在「進度落後時砍什麼」的清單上。
- **雙軌同源**：`chartkit.py` 同時產 PNG／SVG（matplotlib）與 ECharts option。
  加圖型或改樣式**兩軌同時實作**；四條漂移斷言在 `anchors.rendering.drift_assertions`。
- 圖一律自製：只取媒體的圖題與論點，數字出自自己的序列。

## 上下游契約

- **上游投顧知識庫**：實際路徑 **`/Users/macmini/advisory-rewrite`**
  （`advisory-knowledge-hub` 是系統 id 不是路徑；同名舊 checkout 停在 2026-08-18）。
  `theme` 必須是 `kb-core/advisory/anchors.json` 的 `groups` 那十五組 ——
  **值域的唯一的家在那裡**，`chart.theme_unique` 直接讀它。
- **下游 House View 月報**：直接取 `charts/<date>/*.png`。
  **那個路徑是契約**，而 2026-08-21 證明了不改路徑也可能弄壞它 ——
  推的人不見了。配色與 houseview 綁定，改 `anchors.palette` 會讓那邊的健康檢查 FAIL，
  **那是設計成這樣的**。
- **下游 convergence-weekly**：吃本系統產出。
- **下游投顧儀表板「姊妹庫晨間匯流條」**：每天讀 `data/index.json` 的
  `days[0].date` 與 `days[0].headline`。改 index schema 保留這兩個鍵 ——
  改了那格會安靜消失、不報錯。
- **index.json 有兩種方言**：2026-08-20 之前的 entry 有 `slots` 沒有 `kinds`，
  之後的相反。舊 entry 不回頭改寫。
