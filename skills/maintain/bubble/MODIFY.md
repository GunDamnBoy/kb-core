# 執行修改

第 4 步的細節。**拿到使用者對「要改什麼」的確認之後才讀這份。** 標準流程以 `MAINTENANCE.md` 第 2 節為準。

## 設計不變量（新做法先對照這五條）

- **數字一律有來源。** 抓不到的來源沿用上一次的值與 `asof`，失敗記進 `meta.lastAutoRun.fail`；連舊值都沒有就把 `score` 設 `null`，讓它顯示灰燈並退出當層平均。這是整套系統的根本契約，寧可空著也不要猜。
- **權重只放在層級**，22 個指標不各自帶權重欄位（第 6.6 節）——22 個可調參數等於 22 個漂移面；加減指標本身就是在調權重。
- **觸發器維持離散門檻**，與連續的綜合溫度分開呈現（第 6.5 節）：折成分數併進去，溫度會在門檻附近來回跳。
- **會隨數值變動的敘述交給引擎生成**：自動指標寫進 `sub` 由引擎產出，`note` 只留結構性說明（第 6.4 節）。**質化指標相反**——它們沒有引擎可生成 `sub`，`note` 必須留「上週分數 → 本週分數 ＋ 理由」的軌跡。
- **情緒源被擋就換一個不擋機器人的來源**：`senti` 留在 L1（AAII／CBOE 被擋不是拿掉它的理由，拿掉等於改了 L1 的權重結構）。

動 workflow 時，**結尾的 `POST /pages/builds` 步驟必須留著**：`GITHUB_TOKEN` 推的 commit 不會觸發 Pages 佈建，這是 GitHub 的防迴圈設計不是 bug（第 6.2 節）。`MAIN.md` 硬規矩裡的 `history` 只附加、既有筆數原樣保留，改動時同樣適用。

## 步驟

1. 先跑一次 `python3 healthcheck.py` 記下現況（改壞了才知道是不是自己弄的）。
2. 改 `AGENT_BRIEF.md`（規格）。
3. 改 `scripts/update_data.py`（引擎）。動到 `to_quarters`／`pw`／`vix_score`／`bucket`／`gsy_stats`／新聞解析時，**跑 `python3 scripts/update_data.py --selftest`**。
4. 動到 `data.json` 結構時，**「幾處一組」六處全部一起改**（六處的清單在 [`DRIFT-AUDIT.md`](DRIFT-AUDIT.md) 第四節）。
5. 只在**流程或人機分工改變**時才動排程 prompt，用 `mcp__claude-code-remote__update_trigger` 同步。**`prompt` 是整份取代，不是局部編輯**：先讀現有全文，送出前確認所有段落都帶上了，漏掉的段落等於刪除。
6. 在 brief 第 10 節加變更紀錄，**寫清楚為什麼改**，不只是改了什麼；事故經過與被否決的選項寫進 `MAINTENANCE.md` 第 6 節；已知的坑或待辦有變化就同步 `MAINTENANCE.md` 第 4、5 節。
7. 交付照 [`PUBLISH.md`](PUBLISH.md)。
8. 本 skill 若因這次維護而過期：用 save_skill（overwrite: true）更新整支 `maintain` skill，**並把 `bubble/` 這幾份放進交付檔，同步 repo 內 `skills/bubble-maintain/` 的複本**——直接改快取檔不會生效，兩份不同步就是漂移。

## 驗證

**全數通過才算完成**；任何一項失敗就回上一步，不要往下走。

- `python3 healthcheck.py`：沒有新的 FAIL，WARN 只剩已知的那幾項。
- 動到引擎：`python3 scripts/update_data.py --selftest` 通過。
- 動到 `index.html`：抽出 `<script>` 區塊後 `node --check`（healthcheck 已含此項），並實際開一次頁面確認象限圖、觸發器列、台股區都有畫出來。
- **再叫一次子代理**，照 [`DRIFT-AUDIT.md`](DRIFT-AUDIT.md) 做 brief ↔ 排程 prompt ↔ 引擎的獨立比對，確認這次改動沒有製造新的漂移、也沒有在瘦身時弄丟關鍵規則。大改動最容易在自己身上留下新的不同步。
- 線上驗證：等使用者本機推送完成，照 [`PUBLISH.md`](PUBLISH.md) 代為驗證（推送前沒有東西可驗）。
