# 漂移比對清單

第 2 步用，改完之後的複驗也用同一份。**派工前完整讀一次，把這份清單交給 Agent 子代理。**

給子代理的共同要求：逐項給「相符／漂移／不適用」，判為漂移的指出行號與原文、並說明哪一邊是對的；只回報不一致處（改進建議這次不需要）；看起來像 token 的字串一律不複製貼上。

## 一、`AGENT_BRIEF.md` ↔ 排程 prompt

- **先查這一條：排程 prompt 的第一步有沒有「完整讀一次 `AGENT_BRIEF.md`」。** 整個文件分工建立在這條指向鏈上——brief 承擔事實細節、prompt 只留流程骨架。鏈一斷，rubric、燈號界、覆寫禁令的例外全部拿不到，而且從 prompt 本身看不出缺了什麼。
- 執行時刻與 cron：brief 第 8 節 vs 排程設定 vs workflow 檔。
- 人機分工：brief 第 8.1／8.2 節的清單與 prompt 裡的清單**逐項**相符（列出只出現在其中一邊的 id；`stage.current`／`tsmc_52w`／`twii_pos` 這類單項最容易被漏掉）。
- **「絕對不要重抓 `events`／`triggers` 與所有自動指標」這條禁令有沒有同時出現在兩份**，以及 `events` 可補 1–2 條（附 url）的例外。這是最容易漂移也最傷的一條——漏掉會讓覆核用殘值蓋掉好資料。三段理由要在文件裡站得住：
  - 覆核容器的網路有兩條路、能力不同：Bash 的 `curl`／`requests` **只通得到 `github.com` 與 `raw.githubusercontent.com`**（FRED、Stooq、SEC、TAIFEX 一律連不上，**連 `gundamnboy.github.io` 都連不上**），而通得到外網的 `WebSearch`／`WebFetch` 讀 CSV／JSON 端點只會拿到亂碼。禁令的真正理由不是「連不到網路」，是**能連到網路的那條路拿不到引擎要的東西**（對照表見 brief 第 8.3 節）。
  - `events` 是每日 Google News 管線的產出，覆核時重寫等於把新的換成更舊的（`MAINTENANCE.md` 第 6.3 節）。
  - 重抓與重算是兩件事：`quadrant`、`dims`、`composite`、`tw.subs`／`tw.heat` 由指標分數導出，質化分數一改就**必須**重算（brief 第 8.4 節）。
- **收尾重算的順序共七步**，兩份是否一致：指標 `zone` → 層分數 → `composite` → `quadrant` → `tw.subs`／`tw.heat` → `history` 附加（含 `quad` 與 `trig`） → `meta.built`／`meta.builtTime`（`meta.lastAutoRun` 維持原值）。第七步最容易被當成不重要而漏掉，但 healthcheck 硬性要求 `history` 最後一筆的日期等於 `meta.built`，漏掉會直接 FAIL 擋住交付。
- 質化指標的 rubric（brief 第 4.5 節）與 prompt 裡的評分指示。
- `note` 必須記錄上週分數與變動理由這條規則；`asof` 一律填資料本身的日期。
- **覆核端取「上週基準」的規則與 `params` 生效延遲**（brief §8.2）：`history` 沒有 `regime`（要用倒數第二筆的 `quad` 反推）、觸發器點亮數新舊筆讀法不同；改 `params` 不會當場改變頁面，等下次引擎跑才生效，**`triggers.state` 一律保持引擎寫入的值**（為了讓畫面一致而手改它，就是在製造假資料）。兩份對這些的說法是否一致。
- **交付方式**（2026-08-10 起）：三個交付檔（patch／`data-YYYY-MM-DD.json`／離線 HTML，檔名格式要對得上 `bubble-publish` 的 glob）、commit 訊息格式、內嵌 HTML 的 history 裁 60 筆、「不嘗試 push、不做線上核對、不索取或使用 token」的禁令——兩份是否一致。
- 推播摘要的格式與「⚠ 警示」的觸發條件（「還沒發布」不算警示）。
- **排程 prompt 遺漏了 brief 的哪些關鍵規則。**

## 二、`AGENT_BRIEF.md` ↔ `scripts/update_data.py` ↔ `index.html`

本系統獨有、也最容易漂移的一面。

- 指標數量、`id`、所屬層，三處是否一致。
- 特殊計分規則（VIX 非單調、Greenwood-Shleifer 校準）在 brief 與 `vix_score`／`gsy_stats` 是否相符；**方向相反指標的兩套慣例**（取負號 vs 遞減錨點——判斷法看 `anchors` 的 y 遞增或遞減，弄錯分數完全相反）；**錨點不在 `data.json` 裡的指標**（healthcheck 對它們一律跳過，brief 是唯一規格來源，清單見 brief §4.4）。
- 台股子群定義與權重（brief 第 4.6 節 vs `subs_def`／`wmap`）、`TW_BASKET` 的 10 檔；**null 子群會被剔除重新歸一**——某組從 null 補齊那天 `tw.heat` 必然跳一次且方向可上可下，這是設計不是故障（詳見 brief §4.6 與 healthcheck 的 WARN 模擬值）。
- 觸發器 7 項的 `id`、門檻、`note`、`prog`（距門檻進度 0–100%，引擎逐日重算，`megaipo` 恆 `null`，前端缺值不畫）。
- brief 第 6 節的 schema vs 實際 `data.json` 的鍵 vs `index.html` 的 render 函式。
- **`index.html` 讀了引擎沒寫的鍵**：缺鍵或缺欄位會畫出 `NaN`，正解是「缺值就不畫」而不是補假值。`charts.spreads` 這一塊 `healthcheck.py` 已做機械對帳，子代理要看的是**其他還沒被涵蓋的 `DATA.*` 讀取**（`charts` 其餘子物件、`params`、`stage`、`tw.*`）。
- **render 函式裡寫死的敘述文字**：這些不在 `data.json` 裡，healthcheck 抓不到，只能靠讀——問「這句話明年還會是對的嗎」。
- brief 第 9 節的已知失效來源 vs `meta.lastAutoRun.fail` 的實際內容。兩個方向都已經有機器在看：新失敗來源 healthcheck 會報；反向（該退場的）由引擎累計 `meta.lastAutoRun.streak`（成功 +1、失敗歸零），連續成功次數達 `OK_STREAK_RETIRE` 門檻時 healthcheck 會 WARN 提醒把該來源從 §9 與 `KNOWN_FAIL` 一起移除。**子代理真正要靠讀的只剩一件事：§9 寫的「目前處置」是否還符合引擎現在真正的降級行為。**

## 三、`AGENT_BRIEF.md` 內部自我一致性

- 同一個數值在不同段落是否打架（權重、錨點、天數、筆數上限、**各層的指標項數**）。
- **「質化指標佔總權重 X%」是否還算得出來**：依等權規則實算 Σ（層權重 × 該層質化項數 ÷ 該層總項數）。加減任何一個指標都會動到它，而且沒有人會記得回來改。
- 上文的流程敘述是否已被下文的修正取代卻沒改。
- 第 5 節的函式地圖是否還反映 `update_data.py` 的實作（含簽章）。
- 交叉引用是否有效——寫「rubric 見 4.5」時，第 4.5 節真的有那一列嗎。
- `MAINTENANCE.md` 第 5 節的待辦是否已經解決卻沒刪。

## 四、「幾處一組」——改 `data.json` 結構時，這六處一起動

完整定義以 brief 第 6 節末為準。

1. `AGENT_BRIEF.md` 第 6 節的 schema。
2. `scripts/update_data.py`。
3. `index.html` 的 v2 render 函式——`renderQuad`／`renderTriggers`／`renderTwV2`／`renderTwProse`（最容易被忘記：它讀 `tw.items`、`tw.heat`、`composite` 生成台股解讀文字）與圖表區。**漏掉 render 時頁面不會報錯，只會靜靜地少畫一塊。**
4. `index.html` 內嵌的 `<script id="dashboard-data">`：fetch 失敗時的離線退路快照。它不必每天更新，但**改 schema 或改版時要重灌**，否則離線開啟會退回舊架構的頁面。`healthcheck.py` 會比對它的版本與脫節程度（門檻刻意鬆——快照本來就是舊的拷貝），小幅漂移機器抓不到，靠人記得重灌。
5. **`healthcheck.py` 自己，最常被漏掉。** 它的硬寫常數（`LAYER_N`／`QUAL`／`TRIG`／`KNOWN_FAIL` 等）是規格的機器拷貝——加減指標、改層歸屬、改觸發器、改失效來源白名單都要同步改它。漏掉的下場不是靜靜少畫一塊，而是**整條每週流程被自己的檢查擋住**（各常數的嚴厲度分級見 brief 第 6 節）。
6. **外部第六處**：投顧匯流條讀的 `composite`／`tw.heat`／`meta.built` 三鍵、匯流報存的七項指紋（見 [`FILES.md`](FILES.md)「外部相依」）。本系統這邊不用改，但要在交付說明裡提醒使用者轉去 `advisory/MAIN.md`／`convergence/MAIN.md` 同步。
