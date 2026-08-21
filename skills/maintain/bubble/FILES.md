# 檔案分工、系統形狀與外部相依

第 1／2 步查漂移時對照用，決定「新東西該寫哪一份」時也看這裡。

**完整分工表以 `AGENT_BRIEF.md` 第 2 節為準**——它列的檔案比這裡多，`healthcheck.py` 與 `bubble/` 這份維護文件也都是要維護的規格載體。最常用的四份：

| 檔案 | 只放什麼 | 誰讀 |
|---|---|---|
| `AGENT_BRIEF.md` | 現在的規格與判斷規則，含 `data.json` schema | 每週覆核排程每次完整讀一次；維護者 |
| 排程任務的 prompt | 流程骨架：順序與分支判斷、人機分工。事實細節指向 brief 章節，刻意不重抄 | 排程觸發時執行 |
| `MAINTENANCE.md` | 維護說明＋事故與決策檔案（第 6 節）：事故經過、被否決的選項 | 維護者 |
| `index.html` 的 `<script id="update-spec">` | 僅指向 brief 的指標，不放規格 | 讀到這頁 HTML 的工作階段 |

寫東西前先想清楚放哪一份：新的事實細節寫 brief，新的「為什麼」寫 `MAINTENANCE.md` 第 6 節，排程 prompt 只在流程或人機分工改變時才動。

規格另有兩份機器可讀的拷貝，兩份都跟著規格一起改（見 `MODIFY.md` 的「幾處一組」）：`healthcheck.py` 的硬寫常數（`LAYER_N`／`QUAL`／`TRIG`／`KNOWN_FAIL` 等，各常數的嚴厲度分級見 brief 第 6 節），以及 repo 內 `skills/bubble-maintain/` 這份本系統維護文件的複本。

## 系統形狀

模型的骨架是**三個頻率層**，不是概念分類：L1 市場與情緒（日頻）、L2 資金與信用（日～週）、L3 基本面兌現（月～季 nowcast）。這是刻意的——概念分類會把季頻的基本面和日頻的市場擠進同一個平均，日頻訊號被稀釋成一條平線；v1 用概念分類，一個月幾乎不動，這就是改版的原因（`MAINTENANCE.md` 第 6.1 節）。

- 自動更新：GitHub Actions，cron `30 22 * * 1-5` UTC ＝ 台北週二～週六 06:30
- 每週質化覆核排程：`0 1 * * 1` UTC ＝ 台北週一 09:00

（以上兩個時刻在 workflow 檔與排程設定裡才是正本，此處供對照；brief 第 8 節也有一份，三處要一致。）

敘事庫（投顧 `advisory-knowledge-hub` 每日新聞、節目 `podcast-knowledge-digest` 每日專業討論）回答「發生了什麼」「聰明人在想什麼」；本系統是生態系裡唯一的量化庫，回答「客觀狀態是什麼」。完整生態系清單見匯流報的 brief。

## 外部相依（改 schema 或改鍵名前先看這裡）

`history` 的連續性與 schema 的穩定性不是只有自己在用：

- **主題匯流訊號報 convergence-weekly** 每週讀本系統的 `data.json`，2026-08-10 起另存七項指紋做上游改版偵測——本系統改 `dims` 鍵、權重、`triggers`、`zones` 時，匯流報下次備料會亮 🛑。動 schema 前先想一下它的 `renderQuant` 會不會斷。
- **投顧知識庫儀表板的「姊妹庫晨間匯流條」**（2026-08-10 起）每天讀 `composite`／`tw.heat`／`meta.built` 三個鍵，fetch 失敗才退讀頁內 `dashboard-data` 快照。**這三個鍵名要保留**——改了名，投顧那格會安靜消失、不報錯。

這兩處要改名或改意義時，轉去 `advisory/MAIN.md`／`convergence/MAIN.md` 同步；本系統這邊不用做事，但要在交付說明裡寫清楚。
