# AI 泡沫監控儀表板 · 維護

它不解讀行情，它量測 AI 資本循環的體溫——生態系裡唯一的量化庫，每交易日由 GitHub Actions 自動抓取重算。

這套系統壞掉的方式幾乎都是**靜默失敗**：漏改一處 render，頁面不報錯、只靜靜少畫一塊；改了鍵名，投顧匯流條那格安靜消失；線上驗證用錯工具，流程往下走看起來像沒事。所以每一步都拿機器輸出當證據，「看起來正常」不算數。

全程繁體中文（台灣用語）。網站 <https://gundamnboy.github.io/ai-bubble-monitor/>，repo `GunDamnBoy/ai-bubble-monitor`（GitHub Pages 從 `main` 根目錄直出）。

## 硬規矩

- **本工作階段對這個 repo 只讀不寫**（2026-08-10 起）：git push 與 GitHub API 的 repo 端點都被平台的 git proxy 擋（403，自備 PAT 也無效）。發布一律走 [`PUBLISH.md`](PUBLISH.md) 的交付流程；不索取、不使用、不顯示任何 token。
- **數字一律有來源**，抓不到就空著：這是整套系統的根本契約，寧可空著也不要猜（降級寫法見 `MODIFY.md`）。
- **`history` 只附加、同日去重**，既有筆數原樣保留；舊筆帶 v1 的 `D1–D6` 鍵是正常的。象限軌跡與匯流報的跨期比較都靠它。

規矩的來歷、事故經過與被否決的選項在 `MAINTENANCE.md` 第 6 節。

## 第 1 步：載入現況

1. 取得工作副本。唯一權威是 GitHub（本系統沒有本機掛載），公開 repo 直接淺層 clone；已經 clone 過就 `git -C /tmp/bubble pull --ff-only`，確認與 `origin/main` 同步後才判斷現況（曾經在過期 clone 上判斷，結論全錯）。

   ```
   git clone --depth 1 https://github.com/GunDamnBoy/ai-bubble-monitor.git /tmp/bubble
   ```

2. 跑健康檢查，機械式檢查一次做完：

   ```
   python3 /tmp/bubble/healthcheck.py
   ```

   它不改 repo、不連網、不碰 git，會自動偵測 repo 位置（也可用 `--repo <路徑>` 指定）。輸出每行是 PASS／WARN／FAIL，**FAIL 與 WARN 全部帶進第 3 步的報告**。**涵蓋範圍以它的實際輸出為準**（此處不重列清單，清單一定會過期）；機械式與數值型的檢查交給它，你的注意力放在它抓不到的敘述性矛盾——那是第 2 步。

3. 讀 `MAINTENANCE.md` 全部（含第 5 節待辦與第 6 節事故檔案）與 `AGENT_BRIEF.md` 全部（含第 10 節變更紀錄）。
4. 用 `mcp__claude-code-remote__list_triggers` 找到「AI 泡沫監控：每週質化覆核與發布（v2）」，記下 `cron_expression`、`enabled`、`next_run_at`、通知設定，並讀它的 prompt 全文。這個工具的輸出很大、可能超過 token 上限而被存成檔案，那就用 Python 解析：結構是 `{"data": [ ... ]}`，prompt 在 `job_config` 底下。只取需要的欄位，不整段回貼。
5. 讀 `data.json` 的 `stage`（四階段檢查清單本週的證據）與 `events` 前幾條——**這兩塊是你這次要下判斷的材料**，不是驗算；`meta.lastAutoRun` 與 `history` 健康檢查已經印出來了。

完成條件：五項都有實際輸出在手，沒有一項靠記憶或推論。

## 第 2 步：找漂移

系統的每個意義都有**單一來源**：規格在 `AGENT_BRIEF.md`、流程骨架在排程 prompt、實作在 `scripts/update_data.py`、渲染在 `index.html`、「為什麼」在 `MAINTENANCE.md` 第 6 節。**漂移**＝某個意義偷偷長出第二份、而兩份說的不一樣。各檔的權威範圍、系統形狀與外部相依見 [`FILES.md`](FILES.md)。

`healthcheck.py` 抓得到機械式與數值型的不一致；**敘述性的矛盾只能靠讀**，這是這一步最重要的價值。

**固定派 Agent 子代理做獨立比對。** 主線自己讀完常判定「大體同步」，子代理獨立比對才抓得出實質矛盾與遺漏規則——這是既有多套系統反覆驗證過的固定步驟。派工前完整讀一次 [`DRIFT-AUDIT.md`](DRIFT-AUDIT.md)（四個比對面向＋「幾處一組」的六處），把它交給子代理。

完成條件：清單上每一項都有「相符／漂移／不適用」的結論；判為漂移的指出行號、原文，以及哪一邊是對的。

## 第 3 步：報告現況，再問要改什麼

報告用表格或條列，講清楚這幾項：

- **健康檢查**：FAIL 與 WARN 逐條列出，PASS 一行帶過。
- **目前讀數**：`composite`、L1／L2／L3、`heat`／`support`／`regime`、觸發器點亮數、台股 `tw.heat` 與四個子群（子群是 `null` 就一併講——它影響分母，補齊那天 `tw.heat` 會跳）。
- **最近一次自動更新**：日期、成功與失敗項數，失敗項有沒有白名單以外的新面孔。新接入的觀察名單成員（如 CNN F&G，2026-08-10 接入）由 `streak` 見真章——一次失敗照樣追、一次成功還不能從 §9 移除（門檻見 healthcheck 的 `OK_STREAK_RETIRE`）。
- 季度圖表停在哪一季、是不是初步季（幾家已申報、缺誰）。
- 排程：下次執行、是否啟用、有沒有開推播；Cowork 桌面 artifact 的快照停在哪一天。
- **第 2 步的漂移清單**：brief ↔ 排程 prompt、brief ↔ 引擎／網站、brief 內部自打架，各指出哪幾處、哪一邊是對的。
- `MAINTENANCE.md` 第 5 節的待辦與觀察中事項。

使用者問的若是「網站怎麼沒更新／圖表卡住」，先照 [`PUBLISH.md`](PUBLISH.md) 的排查順序定位斷在哪一層，再寫進報告。

完成條件：使用者看完報告、指定了要改什麼，且你把它覆述成一句話得到確認。這一步的產出是報告與那句話，不是任何檔案修改。

## 第 4 步：執行修改

拿到第 3 步的確認之後，讀 [`MODIFY.md`](MODIFY.md) 並照它走——設計不變量、改哪個檔、「幾處一組」的連動、排程 prompt 整份取代的規矩、變更紀錄，以及改完必須全數通過的驗證清單。交付與線上驗證見 [`PUBLISH.md`](PUBLISH.md)。
