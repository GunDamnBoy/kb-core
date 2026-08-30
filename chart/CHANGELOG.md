# 每日五圖｜重建紀錄

## 2026-08-30（日）｜快取被自己刪掉了一段，而預抓說它 ok

這一輪從執行報告的兩條「下一輪要修」進來，追下去發現**那兩條是同一場故障的兩張臉**，
而其中安靜的那一張已經造成了資料損失。另外順手清掉四件從第 2 步漂移盤點掉出來的東西。

### 動到哪些檔

| 檔 | 改了什麼 |
|---|---|
| `scripts/chart/fetch.py` | `get()` 改成**與快取取聯集再寫**（只能長不能縮）；末日倒退拋新的 `SeriesRegressed`；新增 `read_cache()`／`cached_last()`；新增 `--selftest-cache` 五個回歸案例 |
| `scripts/chart/fetch_tw_price.py` | `series()` 加 `have_through` 增量取數（失敗自動退回全量）；新增 `_months_since()`、`selftest_offline()` 與 `--selftest-offline`；CLI 加 `--have-through` |
| `scripts/chart/prep_chart.py` | 「末日最舊的五條」改成 `_stale()`：照日／週／月**各自的**門檻分成硬失敗與警示，硬失敗逐條列、警示只給摘要 |
| `checks/chart.py` | `_series_freshness` 日頻改以交易日計（新 `_weekdays_after()`），帶生效日；`covers`／`blind_to`／fixture／near_miss 一起更新 |
| `chart/anchors.json` | `freshness` 新增 `daily_counts_trading_days`／`trading_days_from`／兩段沿革；`kinds.range_area_is_heavy` 更正結尾那句錯誤預言 |
| `chart/BRIEF.md` | 第三節「不存 option」整段更正並留痕 |
| `skills/chart/SKILL.md` | 第 6 步更正 option；第 7 步加 `window.to` 秒精度；第 9 步**首次寫進 sidecar 那一步** |
| `scripts/chart/RUN-PROMPT.md` ＋ 排程 prompt | 用量那一節指到 sidecar 並附上量測依據 |
| `metrics/MEASURE.md` | 兩處過期宣稱更正，補上七套的 `bounded` 實際分布 |
| `skills/maintain/chart/MAIN.md`／`MODIFY.md` | 欄位名錯字；第 2 步加「快取有沒有變短」；驗證清單加兩支離線自檢 |

### 一、`2408.TW` 與 `2382.TW` 是同一場故障，而安靜的那一張臉刪掉了資料

執行報告寫的是「`2408.TW` 今天第一次回『一筆都沒抓到』」。追下去：

- **2026-08-26 已發布**的 `taiex-quarter-line-without-the-king` 畫得出廣達（`2382.TW`），
  46 點、末日 2026-08-25。
- **2026-08-30 的快取**是 441 點、末日 **2026-06-30**；同期 `2330.TW` 是 483 點。
  差 42 點 ≈ 七、八兩個月的交易日。
- 而預抓把 `2382.TW` 算成 **`ok`**。

機制是三行程式接在一起：`_twse_month()` 在 `stat != "OK"` 或沒有 `data` 時**回空 list**
（註解寫著「非交易月回空 list，那不是錯誤」——對「上個月」那句是對的，對「這個月」不是）；
`series()` 每次**從頭重建 24 個月**，於是尾端兩個月的空缺直接變成序列變短；
`get()` 用 `open(path, "w")` **整檔覆寫**。

> **它當初藏住的方式**：`2408.TW` 24 個月全空 → `series()` 拋錯 → 寫入根本沒執行 → 快取完好、失敗大聲。
> `2382.TW` 只有尾端兩個月空 → 沒拋錯 → 快取被覆寫、失敗安靜。
> **大聲的失敗保護了快取，安靜的失敗銷毀了快取。** 方向反了，而且反得很合理：
> 沒有人會為「成功回傳」寫守衛。

修法不是讓它拋錯就好，是**兩件事一起做，順序不能反**：先與快取取聯集寫回（資料保得住），
再判末日有沒有倒退、倒退就拋 `SeriesRegressed`（失敗仍然大聲，落進預抓的 `failed`）。
只做前者會變成又一個安靜的失敗；只做後者則資料照樣沒了。

**同一個守衛順便補掉第二張臉**：`build_series.materialize()` 會用圖上的 `since` 呼叫
`get()`（例如 `get("SOXQ", since="2026-05-29")`）。當天若預抓跑過，檔頭日期相同會走快取捷徑
而逃過一劫；**預抓沒跑的那天就會把整條 SOXQ 的歷史截成三個月**。這一條到今天為止沒有真的
發生過，`--selftest-cache` 的案例 3 就是它。

### 二、根因是請求量，而抓取順序是證據

台股代號的抓取順序是 `^TWII, 2330, 2317`（CORE）→ `2344, 2382, 2408`（`recent_ids()` 排序後）。
**壞的正是最後兩個，而且嚴重度隨順序遞增**：`2382` 只有尾端兩個月回空，`2408` 全部 24 個月回空。
前四個完好。6 個代號 × 24 個月 ＝ **每天 144 次證交所請求**，而 `anchors.rate_limits`
只訂了「每次間隔 1 秒」，沒有訂總量，也沒有對 `stat != "OK"` 退避
（熔斷只認訊息裡的 `429`，而證交所節流時回的是正常 JSON 加上非 OK 的 `stat`）。

**那是累積節流的形狀，不是代號的形狀。** 所以改增量取數：`get()` 把快取末日交給
`series(have_through=...)`，只補那個月起到本月。同樣六條約 6–8 次請求。
含末日當月而不是從下個月開始，否則會漏掉月中那幾筆。

**沒有量到的部分不寫成已知**：我在沙箱裡打不到證交所（出口只通 pypi），
所以「是節流不是代號」目前是**最強的假說**，不是實測結論。決定性測試一行：

```
python3 ~/kb-core/scripts/chart/fetch_tw_price.py 2408 --months 1
```

通 → 節流成立；不通 → 才是代號本身，那時要查的是證交所的 `stockNo`。

### 三、`chart.series_freshness` 七成時間在響

近十期實測：**七期 WARN、三期 PASS**（PASS 的是 08-21、08-25、08-27）。
原因是結構性的 —— FRED 日頻慢一個交易日，於是週六必然落後 2 個日曆日、
週日與週一落後 3 個，而門檻用日曆日在量。**資料完全正常，是尺不對。**

這與 `weekly_release_source` 是同一題（「同一份規範自己禁止自己」），只是那次只替
H.10 那兩條解掉。**一條七成時間都在響的 WARN，跟一條永遠 SKIPPED 的檢查是同一種失效**：
真的落後四天那天，看起來跟平常一模一樣。

改以交易日計，門檻數字不動、只換尺，帶 `trading_days_from: 2026-08-31`（舊期不回溯）。
換算實測（`_weekdays_after` 六個案例全過）：

| 情境 | 日曆日 | 交易日 | 判定變化 |
|---|---|---|---|
| 週日 08-30 對 FRED 末日 08-27 | 3 | **1** | WARN → PASS |
| 週日 08-30 對股價末日 08-28 | 2 | **0** | WARN → PASS |
| 週一 08-31 對上週五 08-28 | 3 | **1** | WARN → PASS |
| **週三 08-26 對末日 08-24** | 2 | **2** | **維持 WARN** |
| 落後整整一週 | 9 | **5** | 維持硬失敗 |

**假警報消失，牙齒還在** —— 週三只有週一的資料，本來就是落後兩個交易日。

### 四、`prep` 的「末日最舊的五條」把硬失敗擠出了畫面

舊寫法按字串排序取前五。2026-08-30 實測它印出來的是 `2382.TW`（06-30）加四條月頻 FRED
序列（07-01）——**那四條對月頻門檻完全正常**，而真正硬失敗的 `^TWOII`（07-17、落後 44 天）
排第六，**一次都沒有被印出來**。不是「沒有標示」，是根本不在畫面上。
`2382.TW` 雖然有出現，但跟旁邊四條長得一模一樣。

改成照各自門檻判定：硬失敗逐條列，警示只給按末日分組的摘要。
**警示為什麼不逐條列**：換完之後今天警示有 32 條（多數只是日曆日在週末的必然落後），
逐條列會反過來把三條硬失敗埋掉 —— 那等於把同一個病換一個地方犯。
門檻與交易日換算都**從 `anchors` 與 `checks.chart._weekdays_after` 讀**，不在 prep 再寫一份。

### 五、「日檔不存 option」錯了十天，而它寫在「什麼算對」的正本裡

`BRIEF.md` 第三節、`SKILL.md` 第 6 步、`anchors.kinds.range_area_is_heavy` 三處都說不存。
**實測 23 份封存日檔，每一份的 5 張圖都有 option**，近十期穩定佔檔案 21–23%（08-06 那期 50%）。
正確的沿革就在本檔 2026-08-20 深夜〈架構改判：兩軌都留〉：`stored_option` 當時改回 true、
`chart.no_stored_option` 換成 `chart.option_matches_spec`。**anchors 與程式跟上了，那三處沒有。**

> **它當初藏住的方式**：錯的文件不會讓任何檢查變紅。而這一份是「什麼算對的產出」的正本 ——
> 照它做把 option 拿掉，`chart.option_matches_spec` 那四條從真實事故反推的斷言會整組失效，
> **而失效的樣子是「檢查全綠」**（沒有 option 就沒有東西可以驗）。

順帶更正 `range_area_is_heavy` 結尾那句「不存 option 之後這一項會直接消失」——
那個前提從來沒有成立過。體積要算進 `anchors.size` 的預算裡：2026-08-30 那期 232 KB，
離 `json_warn_kb` 250 只剩 18 KB。

### 六、用量那一步以前不在任何文件裡

`usage.csv` 盤點：chart **6 列 `sidecar`、4 列 `commit`**（advisory 4 `sidecar`／7 `window`，
podcast 9 列全 `commit`）。`sidecar` 是可信度最高的那一級，`commit` 切的是 publish 成功的時刻、會偏晚。
差別不在於那幾天比較忙，而在於**這一步沒有寫在 SKILL 也沒有寫在 RUN-PROMPT** ——
六列是輪次自己讀完 `MEASURE.md` 後決定寫的，四列是沒決定的。
**一個每天都要靠執行者自己想起來的步驟，就是一個每天都在賭的步驟。**
現在寫進 SKILL 第 9 步（含完成條件：`usage.csv` 最後一列的 `bounded` 要是 `sidecar`）。

`MEASURE.md` 兩處過期宣稱一併更正（「只有 advisory 的正本有這一步」、
「七套裡只有 advisory 的日檔帶 `window`」——chart 自 08-25 起每期都有）。

### 量測

| 量的東西 | 值 | 怎麼量的 |
|---|---|---|
| 封存日檔存 option 的比例 | **23/23 份、每份 5/5 張** | 逐檔 `json.load` 數 `'option' in c` |
| option 佔日檔體積 | 近十期 20.4–23.1%，全期 20.4–50.1% | `len(json.dumps(option))` ÷ 檔案大小 |
| `series_freshness` 近十期 | **7 WARN／3 PASS** | 逐份執行報告的 `N PASS · N WARN` 那一行 |
| 台股每日請求數 | **144**（6 代號 × 24 月） | `targets()` 順序 × `_months_back(24)` |
| 增量之後 | 約 6–8 | `_months_since(今天, 24)` ＝ 1 個月／代號 |
| `2382.TW` 遺失的點數 | **42**（483 → 441） | 與 `2330.TW` 同期比對 |
| `usage.csv` 的 `bounded` 分布 | chart 6 sidecar／4 commit | `collections.Counter((system, bounded))` |
| `prep` 改法前後 | 硬失敗 0 條可見 → 3 條逐條列（08-31 起 2 條） | 實跑 `prep_chart.py` 與 `prep_chart.py 2026-08-31` |

### 怎麼驗的

- `python3 -m py_compile tools/*.py checks/*.py systems/*.py kbcore/*.py scripts/chart/*.py`
- 檢查自檢（fixture 與 near_miss 兩側）**0 失敗**
- `scripts/chart/fetch.py --selftest-cache` **5 案 8 斷言全過**
- `scripts/chart/fetch_tw_price.py --selftest-offline` **8 斷言全過**
- `scripts/chart/build_series.py --selftest`
- `_weekdays_after` 六個換算案例全過（表在第三節）
- `tools/chart_verify.py` 對 2026-08-30 無非預期 FAIL；並對 08-29 回測確認
  **生效日之前仍走日曆日那條**
- 兩個 repo `find . -type l` 歸零；`anchors.json` 與全部 `data/*.json` 可 `json.load`

### 怎麼倒回去

- 交易日門檻：`anchors.freshness.daily_counts_trading_days` 設 `false`，
  或把 `trading_days_from` 改成未來日期 —— **程式不用動**，這是它帶生效日的用意。
- 增量取數：`fetch.py` 那一行改回 `TW.series(ident)`（不傳 `have_through`），
  立刻回到全量重建。合併守衛與它是獨立的兩件事，可以只退一邊。
- 合併守衛：`get()` 末尾那個 `raise` 拿掉就退回「只合併不報錯」；
  整段拿掉才會回到覆寫。**不建議** —— 那正是這一輪要修的東西。
- 文件類全部是純文字，`git revert` 該檔即可。

### 當時已知的風險

1. **增量取數今天沒有實測過。** 沙箱出口只通 pypi，打不到證交所。
   明天 11:00 的預抓是它第一次跑真的。使用者選擇「直接上線但寫成壞不了的形狀」：
   增量拿不到東西會自動退回全量，而合併守衛保證快取不會變短，**最壞情況是白跑一趟**。
   **驗收方式要能分辨「沒生效」與「生效但沒效果」**：看預抓的耗時
   （今天 9 分 07 秒，六條台股各 24 個月是其中的大頭）與 `2408.TW` 還在不在 `failed`。
   若耗時明顯下降而 `2408` 仍失敗 → 增量生效了但根因不是節流，回頭查代號。
2. **交易日不認國定假日。** 台美行事曆不同，連假之後仍會多算一到兩個交易日。
   記在 `anchors.freshness.trading_days_blind_to`，沒有引入行事曆相依。
3. **月頻門檻有同一個病，這一輪沒有動。** `gap_days // 30` 算的是經過幾個月，
   不是漏了幾次發布：8 月底手上有 7 月的 CPI 是完全正常的，卻一律判 2 期＝WARN，
   於是五條月頻序列每個月下旬固定變黃。要改它需要跟這次一樣先量一遍，**不要順手改**。
4. **`2382.TW` 已經丟掉的那 42 個交易日，守衛救不回來** —— 它只保證從現在起不再變短。
   來源恢復之後全量重建會把它們補回來，或在 Mac 上跑
   `python3 ~/kb-core/scripts/chart/fetch_tw_price.py 2382 --months 24` 手動補。
5. **證交所熔斷仍然只認 `429`**。節流時回的是非 OK 的 `stat`，`streak` 抓不到。
   增量把請求量壓下去之後這件事的急迫性降低，但洞還在。

## 2026-08-29（六）｜清掉六件積欠的維護，其中三件都是「綠燈的失效」

這一輪處理的六項全部來自 08-25 至 08-29 的執行報告，**沒有一項是新發現的**——
它們每天都被寫進報告，然後每天原樣留到隔天。這件事本身就是這一輪最值得記的：
**寫進報告不等於進了修復佇列。**

### 動到哪些檔

| 檔 | 改了什麼 |
|---|---|
| `requirements.txt` | 新增 `yfinance`（握手客戶端），連同 12 個相依的代價寫在原地 |
| `chart/anchors.json` | `known_exceptions.qa_disposed_from` `null` → `2026-08-25`；`rendering.legacy_json_format` 新增；`kinds._pick._anti` 補 scatter 零線那條 |
| `kbcore/repo.py` | 新增 `day_json()` 與 `write_day_json()`——日檔序列化的唯一的家 |
| `tools/publish.py` | `body` 改走 `day_json()` |
| `scripts/chart/_repo.py` | 把 kb-core 根加進 `sys.path`（讓 chart 腳本能 import `kbcore`） |
| `scripts/chart/render_day.py`／`build_series.py`／`rebuild_option.py` | 三支的寫檔全部改走 `write_day_json()` |
| `scripts/chart/chartkit.py` | 新增 `_date_axis()`；`_label_slots` 改跨軸；scatter 零線改讀 `ch.zero_line` |
| `skills/chart/SKILL.md` | 第 4 步補上 `about.qa_dispositions` 的確切形狀 |
| `scripts/chart/RUN-PROMPT.md` ＋ 排程 prompt | exit 11 的處置補上「先問那一天真的發布過嗎」 |

### 六件事各自「當初藏住的方式」

1. **yfinance 從來沒有被宣告過。** 握手那條路 08-22 就寫好了，`anchors` 登記了五條代號，
   `fetch.py` 也實作了——**唯獨沒有人把套件裝進去**。四天的執行報告都寫著
   「連續第 N 天同一個原因」，把症狀當成新聞記了四次。
   **藏住的方式**：失敗是大聲的（`handshake.failed` 每天都有東西），
   但它每天長得一模一樣，於是變成背景噪音。
   **`requirements.txt` 沒列的東西，不會有人幫你裝。**

2. **`qa_disposed_from` 空轉了五天。** SKILL 第 4 步實際上從 08-25 起每一期都在寫
   `about.qa_dispositions`，而檢查每天回 SKIPPED。
   **藏住的方式**：**一條永遠 SKIPPED 的檢查，與一條不存在的檢查，在輸出上長得一模一樣。**
   兩者都不會變紅，也都不會擋任何東西。

3. **日檔有兩種寫法，而守衛比的是字串。** `publish.py` 寫 `indent=1`，
   `render_day`／`build_series`／`rebuild_option` 三支寫 compact。
   **藏住的方式**：症狀是 exit 11「已存在且內容不同」，
   而 exit 11 的字面意思是「已發布的一期就是已發布的樣子」——
   **一個指向錯誤結論的正確訊息**。08-29 那輪差一點就去掛一份不存在的 errata。
   更糟的是 `rebuild_option.py`：它是修既有封存的唯一合法工具，
   卻會把封存整份重排，**資料沒變而 diff 是全檔重寫**。

4. **x 軸 formatter 與 locator 各自決定、沒有人對過帳。** locator 是自動的，
   formatter 被寫死 `%y/%m`，於是 49 個交易日的窗口印出 `26/07、26/07、26/08、26/08`。
   **藏住的方式**：檢查程式看不到像素；而長窗口的圖（大多數）完全正常，
   只有短窗口會現形。修法不是「標籤去重」——**去重會讓刻度消失，刻度是對的、格式才是錯的**。

5. **末值標籤的讓位以軸為鍵，而疊印跨軸。** 左右軸各一個清單，兩條線永遠不互相讓位。
   **藏住的方式**：08-28 撞上時是**換掉一條序列**繞過去的，
   當期圖看起來沒事，缺陷因此留下來——**繞過去的缺陷不會出現在任何紅字裡**。

6. **scatter 的零線是反方向的雙軌漂移。** 靜態軌無條件畫 `axhline(0)`＋`axvline(0)`、
   不讀 `zero_line`，互動軌卻老實走 `_apply_zero_line()`——**同一張圖 PNG 有、網頁沒有**。
   **藏住的方式**：08-24 那張 scatter 兩軸都是報酬率、原點有意義，看起來沒事；
   08-25 兩軸都是水準值，620 個點被壓進畫面六分之一，而檢查全綠
   （17 PASS · 1 WARN · 0 FAIL）。`option_matches_spec` 只問
   「option 有沒有忠實編碼 spec」，**它從來不問 PNG 有沒有多畫東西**。

### 怎麼驗的（全部是當場量的，沒有估算）

- `py_compile` 五個目錄、檢查自檢（fixture ＋ near_miss）**0 失敗**、
  `build_series.py --selftest` 通過。
- **`chart_verify` 2026-08-29：`17 PASS · 1 WARN · 0 FAIL · 1 SKIPPED`
  → `18 PASS · 1 WARN · 0 FAIL · 0 SKIPPED`。** 唯一的 SKIPPED 變成 PASS，
  這正是第 2 項的預期效果，沒有第二個檢查跟著動。
- 生效日回測：`chart.qa_disposed` 在 08-24 回 SKIPPED（早於生效日）、
  08-25／26／28／29 全部 PASS（1/1、6/6、6/6、1/1 筆）。08-25 之前那 12 期
  「有旗標、零處置」照 MAIN.md 的規矩回 SKIPPED，不是 FAIL。
- `chartkit_smoke.py` **9/9 種圖型畫得出來**。
- 三張圖在暫存 repo 重畫後**實際看過**（封存一個位元都沒動）：
  x 軸由 `26/07、26/07、26/08、26/08` 變成 `07/01、07/15、08/01、08/15`，
  長窗口的圖仍是 `%y/%m`（無回歸）；重現 08-28 的雙軸案例（高收益 OAS 2.63 對 VIX 14.51，
  軸內相對位置 0.000 對 0.015、差 0.015 遠小於門檻 0.06），兩個標籤**分開了**；
  重畫 08-25 的 scatter，620 個點填滿畫布，`reading` 說的「近乎垂直的線」現在看得見。
- **改了 `publish.py`，所以照 MODIFY.md 在 `/tmp` 另建 bare origin ＋ 工作 repo 跑端到端**
  （沒有碰任何真 repo）：第一次 `exit 0 @ pushed`，`git ls-tree` 確認遠端
  同時收到 `data/2026-08-30.json` 與 `charts/2026-08-30/` 的 10 個檔；
  再交同一份草稿 → `exit 0 @ already-published`。
  **針對 08-29 那個症狀的直接回歸**：同一份 doc，舊寫法（compact）與 publish 的
  `body` 不同 → 守衛開火 exit 11；新寫法相同 → 不開火。
- 22 份封存全部可 `json.load`；`anchors.json` 可 `json.load`；
  `index.html` 抽 script 後 `node --check` 通過；兩個 repo 的 symlink 各自歸零。

### 順帶量出來的一件事（沒有修，登錄在 anchors）

逐檔盤 22 份封存的字面格式：**08-05 至 08-17 有 12 份是 compact，08-21 之後全部 indent=1**
（08-10 例外，應是事後補發過）。**這條分界線與 `rendering.legacy_dialect` 完全重合**——
都是 08-20 重建的前後，因為重建之後寫入者換成了 `publish.py`。
封存不改寫，所以那 12 份維持原樣；代價寫進 `anchors.rendering.legacy_json_format`：
**現在拿 `rebuild_option.py` 修它們任何一份，會順手把整份重排，diff 變成全檔重寫。**

### 怎麼倒回去

六項互相獨立，可以逐項倒：

- yfinance：`requirements.txt` 刪那一段；已裝的套件留著不影響任何東西。
- `qa_disposed_from`：改回 `null`，`chart.qa_disposed` 立刻回到每天 SKIPPED。
- 共用寫入函式：`publish.py` 的 `body` 改回 `json.dumps(draft, ensure_ascii=False, indent=1)`，
  三支腳本改回 `separators=(",", ":")`——**但那等於把 exit 11 的假警報放回來**。
- chartkit 三項各自獨立：`_date_axis(ax)` 改回 `set_major_formatter(DateFormatter("%y/%m"))`、
  `_label_slots.setdefault("__all__", [])` 改回 `setdefault(axis_key, [])`、
  scatter 的 `if ch.zero_line:` 拿掉。**已發布的 PNG 不受影響**（封存不重畫）。

### 當時已知的風險

- **`chartkit.py` 不只 chart 在用。** `scripts/research/assemble.py`（外資報告週摘，
  週日 23:00）也 import 它，`checks/houseview.py` 會讀它的全文。
  三項改動都經過 `chartkit_smoke.py` 的九種圖型，但**那支不畫外資報告的實際版面**——
  **下一期週摘（08-30 深夜）是第一個真實驗收點**，值得看一眼它的圖。
- **`_date_axis()` 會在 `get_xticks()` 時觸發 locator**，所以必須在畫完資料之後呼叫。
  兩個呼叫點都放在繪圖之後，但**若之後有人在別的地方加第三個日期軸圖型，
  順序放錯的樣子是「格式退回 `%m/%d`」而不是報錯**。
- **`qa_disposed` 現在會擋發布。** SKILL 第 4 步已補上確切的 JSON 形狀，
  但那是文件，不是守門人——**下一輪如果把 key 拼錯，會拿到 exit 10 而不是靜默通過**。
  那是刻意的，但要有人知道。
- yfinance 未釘版本：壞掉的形態是「Yahoo 改了、舊版跟不上」，
  釘住只會讓我們卡在壞掉那一版。**壞掉是看得見的**（空表當失敗拋、記進 `handshake.failed`）。
- ~~**第 1 項還沒完成。** 宣告了不等於裝了~~ —— **當天稍後已在 Mac 上裝好並實測，見下。**

### 補記（同日 12:35）：yfinance 裝好了，而 `^TWOII` 是另一回事

在 Mac 上裝好之後逐條實測握手清單五條（唯讀探針，每條只打一次）：
`^KS11` 2,447 點末日 08-27（落後 2 天，警示）、`005930.KS` 2,447 點末日 08-28、
`8035.T` 與 `6857.T` 各 2,464 點末日 08-28（三條可用）。
**握手那條路本身是好的**，客戶端層的封鎖確實靠它解掉了。

**但 `^TWOII` 落後 43 天、末日凍在 2026-07-17。** 08-08 量到的是 22 天——
不是固定延遲，是**這條序列在 Yahoo 上停止更新了，而且還在惡化**。
對照組決定了結論：同日 `8069.TWO`（櫃買個股、走櫃買官方端點）末日 08-27，
所以不是櫃買資料拿不到，是**櫃買的「指數」在這條路上死了**。留在允許清單裡，
因為官方端點仍只給個股與加權指數，FRED 無等價、也沒有 ETF 代理——**還是沒有第二條路。**

**要記的是它的失敗形狀變了。** 在此之前它每天落在 `handshake.failed`，是大聲的失敗；
從明天起它會落進 `ok`，預抓涵蓋率從 33/48 往上跳，看起來像進步，
**而它依然過不了 `freshness` 的硬失敗門檻**。
**失敗沒有變好，只是變安靜了**——這正是 `data_paths.streak_note` 講的那個形狀，
換一個位置又長了一次。已登錄進 `SOURCES.md` 與 `rate_limits.handshake_allowlist`。

**驗證指令自己也錯過一次**：第一版漏了 `CHART_REPO`，而 `fetch.py` 在 import 時就
呼叫 `_repo.repo()`——**失敗訊息長得像資料 repo 找不到，實際上安裝是成功的**。
`yahoo_handshake()` 本身用不到資料 repo（它只讀 kb-core 的 anchors），
是模組層的副作用把環境變數變成了必需品。

## 2026-08-25（二）｜errata：scatter 的零線把水準尺度的散點壓進角落

`data/2026-08-25.json` 已於 11:46 發布（commit `447a515`，回執 exit 0），
**封存不改寫，errata 記在這裡**。

### 一、slot 4 的 scatter 在水準尺度下不可讀（**這一期的實質缺陷**）

當期第四張 `yen-nikkei-link-came-loose` 用美元兌日圓（約 140–164）對日經 225
（約 31,000–72,400）畫 620 個點。`chartkit.render_static` 的 scatter 分支
**無條件**畫 `ax.axhline(0)` 與 `ax.axvline(0)`（第 458 行），
matplotlib 因此把座標軸撐到原點，**620 個點全部擠在右上角約六分之一的畫面裡**。

- **資料是對的、欄位是齊的、檢查是全綠的（17 PASS · 1 WARN · 0 FAIL）。**
  `kind_data` 只驗 `pts` 在不在，`option_matches_spec` 只驗 option 有沒有忠實編碼 —— 
  沒有任何一條在問「這張圖看得出它要講的事嗎」。
- 更糟的是 `reading` 寫著「這一段在圖上是一條近乎垂直的線」。
  **圖上看不出來**，那句話因此變成一個讀者無法驗證的宣稱。
  這與 2026-08-05 waterfall 那次同型：**圖上的結論與文字對不上，而不丟任何例外**。
- **零線在 scatter 是有條件的，不是常態。** 08-24 那張 scatter 兩軸都是報酬率、
  原點有意義，所以看起來沒事；08-25 兩軸都是水準值，原點在資料範圍外好幾個數量級。
  `zero_line` 這個欄位在 scatter 分支根本沒有被讀。
- **下一輪要修的**：讓 scatter 的零線改讀 `chart.zero_line`（預設 false），
  與其他圖型一致；並在 `anchors.kinds._pick` 的 `_anti` 補一條
  「**兩軸都是水準值的 scatter 不要畫零線**」。修好之前，
  scatter 一律只用「變動對變動」（報酬、基點差、年增率），不用水準對水準。
- **選題層面的替代做法**（今天就該這樣做）：橫軸取日圓 20 日變動 %、
  縱軸取日經 20 日變動 %。原點自然落在資料中央，零線變成有意義的參考線，
  而且「變動對變動」本來就是檢驗連動關係比較誠實的問法 ——
  水準對水準的相關係數 0.699 有很大一部分只是兩條都在趨勢裡。

### 二、slot 3 的兩個 marker 標籤互壓（排版，次要）

`the-long-end-moved-least` 標了 2026-08-14 與 2026-08-21，相距 5 個交易日，
在 8 個月的 x 軸上幾乎重疊，「上週起點」與「上週終點」兩個標籤疊在一起。
`chart.footer_lines` 只量頁尾、marker 沒有任何檢查在看。
**下一輪**：相距少於某個比例的 marker 只留一個，或把第二個錨點寫進 `note`。

### 三、流程上真正的教訓：**看圖要排在交草稿之前**

SKILL 第 6 步的完成條件是「五張圖的 PNG 與 SVG 都產出了，且新圖型在瀏覽器裡看過」，
而 scatter 與 grouped_bar 都在 08-24 用過，**照字面走就不必看圖**。
於是本輪的順序變成：驗 → 交草稿 → 才去看 PNG，
而 publish 每 60 秒掃一次、10 秒靜置就收走 —— **看到問題時已經發布了。**

「首次使用新圖型才看圖」這條規則的隱含假設是「同一個圖型今天不會出新問題」，
而這一次出問題的**不是圖型，是資料的尺度**：同一支 scatter，
08-24 兩軸是報酬所以沒事，08-25 兩軸是水準就壞了。
**該綁的變因是「這張圖的資料形狀有沒有變」，不是「這個 kind 有沒有用過」。**

**下一輪要改 SKILL 第 6 步的完成條件**：五張 PNG 一律實看一次，而且要在第 7 步之前。
一張圖的成本是一次 Read，遠低於一次 errata。

### 四、`window.to` 比實際交草稿晚了 5 分鐘（自述 vs 量測）

當期日檔的 `window.to` 是 `2026-08-25T11:52:00+08:00`，**那是交草稿之前先填好的預估值**。
量到的是：草稿檔 mtime 11:46、回執 `at` 2026-08-25T03:46:52Z＝台北 11:46:52。
兩者差約 5 分鐘。`window.to` 是 `metrics/MEASURE.md` 列的第二可信上界（`window`），
**而它在這一期是自述不是量測** —— 先寫好一個時刻、再去做那件事，
寫出來的數字一定看起來很合理。本輪的 usage sidecar 因此用量到的 11:47，
`bounded` 會記成 `sidecar` 而不是 `window`。
**下一輪**：`window.to` 一律在草稿落地、`wc -c` 確認之後才回填。

## 2026-08-22（二）｜把「限流退避」與「必要的握手」拆開

起點是一個提問：yfinance 的資料看起來更廣，對製圖有沒有幫助。
查下去發現廣度不是抽象的 —— `data/series` 裡 19 條非美標的與指數
（三星、東京威力科創、愛德萬、`^SOX`、`^KS11`、`^NDX`、`^RUT`、`^DJI`、`^STOXX50E`……）
**全部凍在 2026-08-19**，那些是曾經畫得出來、現在畫不出來的題目。

### 量測（三輪，兩個結論、一個仍未知）

- **Yahoo 的封鎖是客戶端層，不是機器。** 同一台 Mac、同一個 IP、相隔幾秒：
  裸 urllib＋固定 UA 第一個請求 HTTP 429；yfinance（cookie＋crumb）拿到 `^GSPC`
  5 點、末日 2026-08-21。**更正留痕**：`SOURCES.md` 原本寫「Yahoo 對本機是永久封鎖」，
  依據是 08-14 首測與 08-16 複測 —— **那個結論把客戶端的性質算成了機器的性質。**
- **Stooq 兩輪都沒量到涵蓋率，而兩次原因不同。** 第一輪十條回
  `could not convert string to float: 'e.encode(c+n))'`（探針只擋空 body 與 No data，
  **第三種假失敗「回 HTML／JS」被讀成了「來源沒有這條序列」**）；
  第二輪修好判別後，十條回**同一頁 HTML、同一個 robots meta** ——
  回應與代號無關，講的是端點與客戶端的關係，不是涵蓋率。
  **真正的設計缺陷是沒有對照組**：十條都失敗時，「來源沒有」與「來源不理我們」
  在輸出上長得一模一樣。已補 `AAPL` 對照組與網頁 `<title>`／cookie 線索。
- **仍未知**：Yahoo 是針對我們，還是現在對所有無 cookie 的客戶端一律 429。
  若是後者，「規避」這個詞從頭就用錯了 —— 我們的客戶端只是舊了。
  **沒量到的部分沒有寫成已知**，登記在 `rate_limits.handshake_vs_evasion`。

### 決定與動到哪些檔

**開，但範圍極小、規則明著改。** 規則被默默違反，比規則被公開改掉糟糕得多。

| 檔 | 改了什麼 |
|---|---|
| `chart/anchors.json` `rate_limits` | 新增 `handshake_vs_evasion`（拆開兩件事，並記下未量到的那一半）、`handshake_measured`（08-22 的兩次量測）、`handshake_allowlist`（五條）、`handshake_allowlist_rule` |
| `scripts/chart/fetch.py` | 新增 `anchors()`／`handshake_allowlist()`／`yahoo_handshake()`；`_route_and_fetch` 讓允許清單排在所有路由之前。**清單外呼叫會被擋下來並說出為什麼**；回空表當失敗拋出 |
| `scripts/chart/prefetch.py` | 允許清單展開進 `CORE`（每天替那條路做體檢）；狀態檔新增 `canary`（註明它只答得出「裸客戶端通不通」）與 `handshake`（那條路壞了看得見） |
| `chart/BRIEF.md` §七 | 紅線改寫：限流那條保留，握手另立一條並指路到 anchors |
| `skills/chart/SKILL.md` 第 3 步 | 同上，外加「用了要在 note 寫明來源與取法」與狀態檔 `handshake.failed` 的處置 |
| `chart/SOURCES.md` | 更正「對本機永久封鎖」的措辭、登錄決定與三輪量測 |
| `scripts/chart/probe_sources.py` | 新增（一次性探針）：Stooq 三種假失敗的判別、`AAPL` 對照組、Twelve Data 先 `symbol_search` 再取序列 |

**允許清單只放既沒有等價序列、也沒有 ETF 代理的代號**：櫃買指數、韓綜、三星、
東京威力科創、愛德萬。`^SOX`／`^STOXX50E`／`HG=F` 有 SOXQ／FEZ／CPER，**不進清單** ——
代理不完美但它誠實、而且今天就在跑。

### 怎麼驗的

`py_compile` 全綠、`selftest` 0 失敗、當期 `chart_verify` 維持 15 PASS · 3 WARN · 0 FAIL。
`prefetch.py --list` 由 46 條變 51 條（核心 31→36），五條允許清單都在。
`yahoo_handshake()` 兩側各驗一次：`^GSPC`（不在清單）被擋並說出理由、
`005930.KS`（在清單）在無 yfinance 的沙箱大聲失敗而不是回空。
探針三種情境（找不到代號／找到但取不到／正常）與 Stooq 四種回應
（HTML、空 body、No data、正常 CSV）各驗一次。

### 怎麼倒回去

把 `anchors.rate_limits.handshake_allowlist` 清空 —— `fetch` 讀到空清單就沒有任何代號
走得進握手，`prefetch` 的 `CORE` 也不會多那五條，其餘程式碼留著不會有作用。
要連程式一起撤就刪 `yahoo_handshake()` 與 `_route_and_fetch` 裡那三行。

### 當時已知的風險

- **yfinance 每隔幾個月被 Yahoo 改壞一次**，壞掉的樣子是回空表。已當失敗拋出，
  但**那五條會同時失敗**，看起來像 Yahoo 又整個關門 —— 判讀前先看 `canary` 那一欄。
- **`^TWOII` 取得到不等於能用**：2026-08-08 實測 Yahoo 這條落後 22 天，
  握手取到之後要先看末日。
- ~~**Twelve Data 還沒量。**~~ **當晚量完了**：免費方案＝美股。
  `AAPL@NASDAQ` 拿得到（對照組成立），櫃買指數／韓綜／日經／Stoxx 50 在 `symbol_search`
  找不到，三星／東京威力科創／愛德萬回 404。**清單維持五條，沒有東西可以拿掉。**
  Stooq 連對照組都回同一頁 795 bytes 的機器人頁，**出局**。
  同一輪探針製造了三個假的 ✓（`^SOX`→SOXL 三倍槓桿 ETF、`HG=F`→HG 一家保險公司、
  `DXY`→DXYN），因為它拿代號搜尋的第一個候選就用 —— **三個都回 30 點、末日正確、
  落後 1 天，每一個訊號都說它成功了**。已改成只接受逐字相同的代號並攤開候選；
  詳見 `chart/SOURCES.md`。
- 沙箱裝不了也連不出去，**這條路只在 Mac 上活著**；執行輪次讀的是預抓快取，
  所以沙箱不受影響，但**要驗它只能在 Mac 上驗**。

## 2026-08-22（一）｜四個「每天都做得到、所以沒有人把它變成程式」的地方

08-22 那輪（15 PASS · 3 WARN · 0 FAIL，回執 exit 0 @ `55f2156`）本身沒有失敗，
維護是從它的執行報告倒推的。四件事的共同形狀是：**它每天都做得到，
所以從來沒有變成程式；而做得到的事會在某一天悄悄少做一次，且輸出長得一模一樣。**

### 動到哪些檔

| 檔 | 改了什麼 |
|---|---|
| `scripts/chart/prefetch.py` | 新增 `_write_macro_release()`：預抓完成後在**有網路的那台機器**跑 `macro_release.check()`，寫 `chart-of-the-day/data/_macro_release.json`。失敗時寫一個帶 `error` 的檔，**不是不寫** |
| `checks/chart.py` `_release_day` | 認兩種方言：舊的 list、新的 dict（整份檔）。dict 帶 `error` 且 items 空 → SKIPPED 並把錯誤說出來 |
| `chart/anchors.json` `structure.release_day` | 新增 `detection_runs_in_prefetch`，記下偵測搬家與搬家前的兩次人工重建 |
| `chart/anchors.json` `freshness` | 新增 `weekly_release_series`（`DTWEXBGS`／`DEXJPUS`）＋`weekly_warn_periods` 2／`weekly_fail_periods` 3／`weekly_release_from` 2026-08-22 |
| `checks/chart.py` `_freshness` | 週頻發布序列改以發布期數計；**識別靠 `series_spec` 的 id**，不靠序列名稱 |
| `checks/chart.py` `_track` | 週日那期比對 `payload["prev"]`，與週六同一條軌道 → FAIL |
| `chart/anchors.json` `tracks` | 新增 `weekend_distinct_enforced_from` 與說明 |
| `scripts/chart/scan_moves.py` | 新增。slot 2 的「程式化掃描」終於有程式：只讀快取、不連外，1 日與 5 日變動＋近三年分位，利差與殖利率改報絕對變動 |
| `scripts/chart/chartkit.py` | `render_static` 回傳 `footer_lines`（截斷前）與 `footer_truncated` |
| `scripts/chart/render_day.py` | 把上面兩個寫進圖；`about.rendered_at` 當場量 |
| `checks/chart.py` `_footer` | 有 `footer_lines` 就用量測，沒有才估 |
| `skills/chart/SKILL.md` | 第 1 步讀 `_macro_release.json`、第 2 步用 `scan_moves.py`、第 3 步的週頻門檻、第 9 步用 `rendered_at` 並指向 RUN-PROMPT 的用量段 |

### 量測

- **`DTWEXBGS`／`DEXJPUS` 是週頻發布**：08-21 與 08-22 兩輪的預抓都在當天成功抓到，
  末日都停在 2026-08-14（週五）。照 `daily_fail_days=5` 算，它們**週三就過硬失敗**，
  週三到週日五天不可用 —— 於是連續兩天頭條的「美元走弱」那一半被砍，
  **原因不是資料壞了，是門檻的形狀**。這是月頻那條「同一份規範自己禁止自己」的第二例。
- **`scan_moves.py` 重算 08-22 的掃描**：`GLD +5.45%／96.7`、`SOXQ −5.44%／10.4`、
  `NIKKEI225 −3.93%／6.6`、`SP500 −1.43%／16.0` 與當期封存**逐項相同**；
  唯一差異是樣本數（工具 749、當期手寫 748，因為三年切點的取法差一筆），
  `CPER` 的分位因此由 42.4 變成 42.3。**封存不改寫**，日後以工具為準。
- **頁尾行數（更正留痕）**：08-22 的執行報告與 `about.run` 寫著
  「實際折成三行、檢查估算給兩行，估算比排版引擎樂觀」。拿 `render_static` 量過之後
  **那句話是錯的**：五張圖的估算與量測都是 3／3／2／3／3，一致。
  錯的是報告作者另寫的一套估算法（把 source 與 note 合併後才除），不是這條檢查。
  已發布的 `data/2026-08-22.json` 不改寫，**errata 記在這裡**。
  改用量測仍然值得做，但理由換成正確的那一個：**估算照不到「有沒有被截斷」**。
- **PNG mtime 不能當量測**：08-22 五張 PNG 的 mtime 全被掛載層改寫成 11:50:54，
  晚於實際出圖時刻，而 08-21 的報告正是拿它當「量測」。改由 `about.rendered_at` 當場寫。

### 怎麼驗的

`py_compile` 全綠；`selftest` 0 失敗（`footer_lines` 與 `series_freshness` 的
fixture／near_miss 都補了新路徑，且**兩條路徑各留一張圖**，免得估算那條退路變成沒人驗）；
`build_series --selftest`、`scan_moves --selftest` 通過；
08-22 當期 `chart_verify` 維持 **15 PASS · 3 WARN · 0 FAIL**（改動前後相同）；
08-14／08-17／08-21 回測沒有新增 FAIL（既有的 freshness 紅字是這條檢查的形狀，
`option_matches_spec` 那筆是 08-14 封存本來就有的漂移）。
三條新規則各自用合成 payload 兩側驗過：週末同軌道 FAIL／不同條 PASS／沒有前一期 PASS；
`DTWEXBGS` 落後 8 天 PASS、45 天 FAIL、**沒有 `series_spec` 時退回日頻仍 FAIL**、
生效日之前不套用；頁尾量測 4 行 FAIL／3 行 WARN／2 行 PASS。
`render_day.py` 在 `/tmp` 的暫存 repo 對 08-22 重跑並看圖，**沒有碰封存**。

### 怎麼倒回去

四件事互相獨立，可個別回退：把 `prefetch.py` 的 `_write_macro_release()` 呼叫拿掉、
把 `freshness.weekly_release_series` 刪掉（檢查會自動退回日頻）、
把 `tracks.weekend_distinct_enforced_from` 刪掉（`_track` 讀不到就不比 prev）、
`scan_moves.py` 直接刪。`footer_lines` 拿掉後檢查自動退回估算。

### 當時已知的風險

- **`_macro_release.json` 要等到 08-23 11:00 的預抓才會第一次真的產生。**
  在那之前執行輪次讀不到它，SKILL 要求「說出來」而不是自己去問 FRED ——
  **明天那輪如果照舊用 web_fetch 重建，代表這次搬家沒有真的接上。**
- 週頻清單是**人工登錄**的：FRED 改了某條的發布頻率，這裡不會自己知道。
- 週末同軌道只在**週日那一期**判得出來，週六當下仍然沒有訊號。
- `scan_moves.py` 的預設清單是這次挑的，**它會反過來決定選題半徑** ——
  掃到什麼才會想到什麼。下次擴充預抓核心清單時要一起看。

## 2026-08-21｜靜態產出從來沒被推過：接縫漏掉的第三個維度

首次無人值守輪次發布成功（回執 exit 0、commit `11a81d5`）之後，
問了一句「網站更新了嗎」才發現：**`data/` 上去了，`charts/2026-08-21/` 沒有。**

### 病灶

`publish.py` 第 147 行硬寫 `git add "data"`。`charts/` 不在 `.gitignore`，
只是從來沒有人 stage 它。讀 `.git/index` 確認：`data/` 有 14 筆含當天，
`charts/` 被追蹤的日期停在 **2026-08-17** —— 那些是重建前推上去的。

重建前是 `com.kenny.dashpush`（每 180 秒掃全 repo add+commit+push）順手帶上去的。
08-20 重建時它退場，八個 launchd 工作裡沒有它，而「誰來推 charts/」
**沒有交接給任何人**。不是有人改壞了，是這件事從那天起就沒有主人。

諷刺的是本檔開篇第一句：「決定性的理由是 House View 的 pptx 直接吃
`charts/<date>/*.png` 的路徑 —— 換 repo 等於弄壞一個沒有人在顧的下游。」
**repo 沒換，下游還是壞了**，而且壞在同一條路徑上。

### 為什麼四層防線一條都沒響

| 訊號 | 當時說什麼 | 為什麼看不見 |
|---|---|---|
| 回執 | `exit 0 @ pushed` | push 真的成功了 —— 推的是 `data/` |
| `chart_verify` | 18 PASS · 0 FAIL | 檢查全部跑在發布**之前** |
| `chart.png_present` | 綠 | 讀的是**本機**檔案系統，五個檔確實在、200KB、不是空白圖 |
| `sentinel.data_fresh` | 綠 | 問的是 `data/` 的年齡 |

**檢查驗的是「有沒有畫出來」，沒有人驗「有沒有送出去」。**
這是本系統反覆出現的那個形狀又一次：每一個訊號都說成功。

### 修法：宣告 ＋ 對帳，兩件事分開

1. `kbcore/system.py` 加 `staged_paths(draft, repo) -> list[str]`，**必填、無預設**。
   這是同一道接縫漏掉的第三個維度 —— 前兩個是 `index_entry`（2026-08-20）
   與 `index_meta`（同日），docstring 裡的理由逐字適用於這一個。
   不給預設值是刻意的：`["data"]` 的預設會讓下一套系統安靜地繼承錯的形狀。
2. 三套系統各自宣告：chart ＝ `data` ＋ `charts/<date>`（PNG 與 SVG 都推）；
   advisory 與 podcast ＝ `data`（前者的 `raw/` 由 Actions 那一側自己 commit，
   後者的 Word 與逐字稿刻意留在所有 repo 之外）。
3. `publish.py` 步驟 4b **對帳**：commit 之後問
   `git ls-files --others --exclude-standard -- <宣告的路徑>`，
   非空就寫 `exit 14 @ static-outputs`，**不准寫 exit 0**。
   問的是「這些路徑底下還有沒有沒進版控的檔」，不是「add 有沒有回 0」——
   前者問結果，後者問我有沒有照做。`add` 失敗不拋錯、`commit` 沒東西可提交也回 0，
   所以只驗前者等於沒驗。

### 順帶修掉：`chart.series_freshness` 是一條沒有讀者的檢查

同一輪發現。它讀 `s.get("data") or s.get("points")`，
而 `build_series.py` 與 `render_day.py` 寫出來的序列欄位是 `dates`／`values` ——
13 天封存與當期產出**全部都是**。也就是說它從來沒有讀到任何一個數字，
每條序列都被 `continue` 掉，整條檢查回 `ok()`。
`BRIEF` 第六節第 3 條（序列落後超過硬失敗門檻）等於沒有守門人。

它通得過自檢，因為 **fixture 用的是 `data` 形狀** —— fixture 對得上程式、
對不上產出。所以這次連 fixture 與 near_miss 一起換成真實形狀。

### 量測

- 修好後對當期（2026-08-21）：**17 PASS · 1 WARN · 0 FAIL · 0 SKIPPED**。
  WARN 是 DGS30／兩條 BAML 落後 2 天、布蘭特落後 3 天 ——
  這四筆本來就該是 WARN，當期的 subtitle、source 與 `window.note` 都已寫出實際基準日。
- 檢查自檢（fixture／near_miss 兩側）0 失敗；`py_compile` 全數通過；
  `build_series --selftest` 通過。
- publish 端到端實測（`/tmp` 內另建 bare origin ＋ 工作 repo，**不碰真 repo、不留 index.lock**）：
  `pushed` 一次推上 10 個靜態檔 ＋ 4 個 data 檔；
  `already-published` 路徑重跑仍走 add／commit／push；
  對帳器塞一個未追蹤檔進去會列出它，乾淨狀態下輸出為空。
- 靜態產出體積：當期 1.5MB（PNG 944K ＋ SVG 568K），`charts/` 全目錄 22MB。
  照此速率一年約 550MB，**Pages 的 1GB 軟上限大約兩年內會碰到** —— 記在待辦。

### 怎麼倒回去

`staged_paths` 是新增欄位，移除它並把 `publish.py` 的 `git add -- *paths`
改回 `git add "data"`、刪掉步驟 4b 即可完全回到 08-21 之前的行為。
`checks/chart.py` 的 freshness 改動獨立，可單獨倒回（倒回去它會恢復成永遠 PASS）。

### 當時已知的風險

- **回測舊期時 freshness 一定紅**：`now` 取的是執行當下，不是那一期的日期。
  對 2026-08-14 回測會報 8–9 天落後 —— 那是這條檢查的形狀，不是舊期壞掉。
- ~~`kb-core` 自己有 remote 但八個 launchd 工作裡沒有任何一支推它~~ ——
  **同日解決，見下一節。**

### 同日續：kb-core 自己也沒有人推（第三個病灶）

前一節查 `charts/` 時順手發現：`kb-core` 有 remote，八個 launchd 工作裡
沒有任何一支推它。跟 `charts/` 同一個病 —— dashpush 退場沒有交接。

新增 `tools/push_kbcore.py` ＋ `launchd/com.kenny.kbcorepush.plist`（每 300 秒）。
**刻意不併進 `publish.py`**：

| | `kbpublish.*` | `kbcorepush` |
|---|---|---|
| 推的是 | 機器產生、發布後不可改寫的 `data/` | 人與模型正在改的原始碼 |
| 閘門 | 那一套系統的內容檢查 | `py_compile` ＋ 檢查自檢 |
| 觸發 | outbox 有草稿 | 工作區靜置 5 分鐘且有未推的東西 |
| 落後 origin | `pull --rebase` 續推 | **停下來報告，不自動 rebase** |

最後一列的理由：kb-core 是另外三套排程**執行中所依賴**的程式碼，
在它們跑的時候改寫工作區，等於讓 `import checks` 有機會讀到半成品。
單一寫入者的 repo 落後 origin 本來就代表有人在別處動過 —— 需要人看，不該自動化。

閘門三比前兩道重要：**推壞掉的 `checks/` 上去，三套系統的閘門會同時失效，
而回執照樣說成功。** 一個推不上去的 repo 只是不方便，
一個推上去的壞閘門是靜默失效。

`.push-receipt.json` 必須 gitignore ——不擋掉的話它每輪重寫會讓工作區永遠是髒的，
於是每 5 分鐘 commit 一次自己的回執，而每次 commit 又產生新的回執。
`newest_mtime()` 也把它排除，否則靜置永遠不成立。

**六條路徑在 `/tmp` 實測（另建 bare origin ＋ 工作 repo，不碰真 repo）：**

| 情境 | 退出碼 | 副作用 |
|---|---|---|
| 乾淨且未領先 origin | 13 空輪次 | 無 |
| 有改動但靜置未到 | 13 空輪次 | 不 commit |
| 靜置已過 ＋ 自檢綠 | 0 pushed | origin 前進，訊息標 `chore(auto)` |
| 檢查自檢紅（把今天修的 freshness 改回去） | 10 gate | **origin 未被動到** |
| 語法壞掉 | 10 gate | origin 未被動到 |
| origin 被別處推進 | 15 diverged | **origin 未被覆蓋、無 rebase 狀態目錄** |

第四條特別值得記：注入的回歸就是本節前半修掉的那個 bug，
而它被抓到是因為**這一輪連 fixture 一起換成了真實形狀**。
修 bug 順手把 fixture 修對，於是這個 bug 從此不可能再悄悄回來。

### 同日續：維護文件的正本收進 kb-core

`maintain` 技能的 `chart/MAIN.md` 與 `MODIFY.md` 停在重建之前 ——
路徑寫 `/Users/kenny`、叫人跑已退休的 `tools/check_day.py`、
把 `com.kenny.dashpush` 當成活的（它的殘骸在
`chart-of-the-day/tools/_to_delete/dashpush-auto-push.sh`）。

**一份把退休機制當成活的維護文件，會讓下一個人去修一個不存在的東西。**
而它自己的第一條硬規矩就是「這份維護文件不持有會變的值」——
漂掉的不是數字，是路徑與檔名。

正本改放 `kb-core/skills/maintain/chart/{MAIN,MODIFY}.md`，
跟 `skills/chart/SKILL.md` 同一個做法：**正本進版控，別處那份是副本。**
技能的子檔無法由工作階段更新（`save_skill` 只取代 `SKILL.md`，
其餘檔案原樣保留），所以整包重打 `.skill` 安裝是唯一能整份換掉的路。

**同日第二輪**：既然要重打包，把整支 `maintain`（24 檔、六套系統）
的正本一起收進 `kb-core/skills/maintain/`，並清掉另外兩套活系統的假話。

盤點結果 —— **六套裡只有三套是活的**：投顧（`advisory-daily-0730`）、
五圖（`chart-daily-1130`）、podcast（`podcast-daily-300`），
三套都已接上 kb-core 底盤。bubble／convergence／houseview
**本機沒有排程也沒有 launchd 工作**，文件停在重建之前，待重建。
`convergence/FILES.md` 甚至寫著 taskId `convergence-weekly` —— 那條不存在。

這一輪改的 8 個檔：

| 檔 | 改了什麼 |
|---|---|
| `SKILL.md` | 路由表加上 taskId 與資料 repo 兩欄；後三套標「本機無排程」；加上「系統 id ≠ 路徑」的警告與正本位置 |
| `advisory/MAIN.md` | **repo 根目錄由 `/Users/kenny/advisory-knowledge-hub` 改成 `/Users/macmini/advisory-rewrite`**；`scripts/check.py`／`metrics.py` 改成 `tools/advisory_verify.py`；taskId 更正 |
| `advisory/MODIFY.md` | 表格裡的 `AGENT_BRIEF.md`／`scripts/*`／`search.html` 全部不存在，改成 kb-core 佈局；加上「動到 `groups` 要回頭跑五圖檢查」 |
| `chart/DIAGNOSE.md` | 拿掉 `~/.dashpush/repos.txt` 與 `check_day.py`；「發布了但網站沒更新」拆成 data／charts／Pages 三種 |
| `chart/FILES.md` | 整張檔案地圖換成 kb-core 佈局；加「已失效但還留著的」一區 |
| `podcast/MAIN.md` | dashpush → `com.kenny.kbpublish.podcast`；**加上一段待查項**（brief 可能已降級，當時 repo 沒掛上無從確認） |
| `podcast/FILES.md`、`SYNC-CHECKLIST.md` | taskId `podcast-digest-daily` → `podcast-daily-300` |

**podcast 那份是刻意只做可查證的更正。** `~/podcast-knowledge-digest`
當時沒有掛進工作階段，所以「它的 `AGENT_BRIEF.md` 是不是也像五圖那份一樣
被降級了」無從確認 —— 那件事寫成待查項留在文件開頭，**沒有猜**。

`bubble`／`convergence`／`houseview` 三套的 9 個檔**一個字都沒動**，
用 `diff -rq` 確認過。

## 2026-08-20 深夜｜第四套系統上底盤：輸出契約、12 條檢查、系統註冊

沿用既有的 `chart-of-the-day` 資料 repo，不開新的。

**決定性的理由是 House View 的 pptx 直接吃 `charts/<date>/*.png` 的路徑** ——
換 repo 等於弄壞一個不在重建範圍、也沒有人在顧的下游。
第二個理由是舊規格自己記著「新建的 repo 不會自動納入推送清單」，
那個坑踩過兩次（podcast 8/02、chart 8/05），開新 repo 是把同一類設定風險再進一次。

反方最強的論點是「並行比對三天」，但新底盤給了更好的做法：
`tools/chart_verify.py` 可以對任何一天跑完整檢查而**不產生任何副作用**，
不需要靠兩個 repo 換來。

### 一、架構決定：不存 option，兩軌從同一份 spec 渲染

舊制把 ECharts 的 `option` 存進日檔，於是同一張圖有兩份實作 ——
而舊文件反覆記載**雙軌漂移是這套系統最常見的缺陷類型**。最嚴重的一次是
瀑布圖在網頁上每根從 0 往上長（ECharts 預設 `stackStrategy: samesign`），
**圖上的結論與 `takeaway` 相反，卻不丟任何例外。**

實測 2026-08-17 那期：`option` 佔全檔 **43%**、`series` 佔 32%，兩者內容重複。

**兩種錯的代價不對稱**：雙軌漂移是正確性失效；
「舊圖用新版渲染器重畫會有樣式差異」只是版本問題，在 `about` 記 `renderer_version` 就能定位。

**但規則已定、機制未建。** 渲染器要能從 spec 畫出八種圖型才談得上不存 option，
所以 anchors 加了一個**具名的旗標** `rendering.renderer_ready: false`，
`chart.no_stored_option` 讀它、回 SKIPPED 並說出原因。
不把 `stored_option` 暫時改成 true 的理由：那會讓 anchors 說「我們存 option」、跟 BRIEF 矛盾，
而且未來看不出那是過渡狀態。**「還沒做」與「做過了沒問題」必須分得出來。**

### 二、盤點時我誤判了一次，而那正是要記進契約的東西

看到 18 張非折線圖的 `series` 是空的，一度結論「它們的資料只存在 option 裡，
所以『一年後能原樣重畫』只對 47/65 張成立」。**錯的。**

資料一直都在，只是**每種圖型有自己的欄位**：scatter 用 `pts`、heatmap 用 `cats`/`rows`/`matrix`、
長條用 `cats`/`groups`、waterfall 用 `cats`/`vals`、gauge 用 `gauge`。
**我只找了 `series`。**

那張對照表先前不在任何文件裡 —— 所以「series 是空的」看起來就像資料掉了。
現在它是 `anchors.kinds`，渲染層與檢查程式都照它走，
而 `chart.kind_data_present` 逐圖型驗，13 天 65 張圖全數 PASS。

### 三、`theme` 的值域不在 chart 這邊

`theme` 必須是投顧知識庫那十五個子類別之一 —— 它們是同一份東西。
舊系統把十五個字串硬寫進 `check_day.py` 的 `THEMES`，
2026-08-20 比對發現**兩邊逐字相同 —— 但那是運氣**：沒有任何機制在維持它。

所以 `systems/chart.py` 的 `build()` 把投顧的 anchors 一起讀進來，
`chart.theme_unique` 直接讀它的 `groups`。**投顧那邊改組名，這裡會立刻變紅。**

### 四、回測逼出一條錯的規格

12 條檢查拿 13 天封存跑過。第一輪 `chart.lengths` 有 6 天 FAIL，
**全部是 `standfirst`** —— 正是那個「規格寫著 60–100、`check_day.py` 從來沒驗過」的欄位。

量了才知道規格是錯的：

| 欄位 | 散文規格 | 實測 | 處置 |
|---|---|---|---|
| `headline` | 20–30 | 20–31、中位 27、P75 29 | 帶取 **20–32**（只有一天界外） |
| `standfirst` | 60–100 | 69–126、中位 98、P75 110 | 帶取 **60–130**（**6/13 天界外**） |

「規格與實作連續一週不一致而沒有人擋，代表那條規格從一開始就不可執行。」
而這一條連被違反都沒有被看見 ——
**一個沒有讀者的數字不會被違反，只會被無視**，然後在有人拿它當真的那天集體變紅。

`about.data_path` 同理：實測只有 8/15／16／17 三天有（值都是 `prefetch`），
那是預抓系統落地前後才加的欄位，所以 `known_exceptions.data_path_from = 2026-08-15`，
更早的日檔回 SKIPPED 而不是 FAIL。

### 五、回測結果

13 天 × 12 條：

```
              chart.*（依 id 排序）
  2026-08-05  ––!··✗······
  ...
  2026-08-17  ·····✗······
```

**11 條在 13 天全數 PASS 或 SKIPPED**；唯一全紅的是 `no_stored_option`，
那是設計如此（舊制存了 option，歷史不改寫）。
`footer_lines` 兩筆 WARN 剛好落在 3 行的邊界上，是真的。

自檢也抓到我一個錯：`footer_lines` 的 `near_miss` 我設成 9 行而內容是 10 行，
於是「剛好還在合格側」的樣本也被觸發了。**`fixture` 證明檢查會叫，
`near_miss` 證明它在對的地方叫** —— 這次是後者救的。

### 六、今晚做到哪裡

| 已完成 | 檔案 |
|---|---|
| 輸出契約 | `chart/anchors.json`（24 區塊）、`chart/BRIEF.md` |
| 檢查 | `checks/chart.py`（12 條，全庫 61 條） |
| 系統註冊 | `systems/chart.py`（第四套） |
| 每日步驟 | `skills/chart/SKILL.md` |
| 無副作用的驗證入口 | `tools/chart_verify.py` |
| 資料 repo 接線 | `.kb-data-repo`、`deploy.yml` 加上線驗證、`sentinel.yml` |
| 排程 | `launchd/com.kenny.kbpublish.chart.plist`、`env.py` 登記 |

**還沒做（下一刀）**：

1. **渲染器** —— 兩軌從 spec 畫出八種圖型。這是 `renderer_ready` 翻成 true 的前提，
   也是今晚唯一沒動的大塊。
2. **取數層** —— `fetch.py`／`build_series.py`／`prefetch.py` 還在資料 repo 的 `tools/` 裡。
   **今晚刻意不動它們**：那是目前唯一能產出一天的東西，移掉等於讓管線完全不能跑。
3. ~~`scripts/chart/preamble.md`~~ —— 見下一則，那個指標本身是錯的形狀。

## 2026-08-20 深夜（續）｜雙軌決定、一個活著的 bug、以及一個我自己造的死連結

### 一、架構改判：兩軌都留，改用檢查抓漂移

稍早我把 `stored_option` 設成 false，前提是「只剩一個渲染器」。
使用者選了第三條路 —— **兩軌都留**（PNG 的排版規格不動、互動也不失去），
所以那個前提不成立，`stored_option` 改回 true，
`chart.no_stored_option` 換成 `chart.option_matches_spec`。

**這次改判要記下來的不是結論，是它推翻了什麼。**
我原本以為「兩軌從同一份 spec 渲染」就能解決漂移 —— 讀完 `chartkit.py` 才發現
那 891 行裡本來就是兩套實作（`render_static` 用 matplotlib、`echarts_option` 產 option），
**逐圖型各寫一次**。同一份 spec 只是讓它們從同一個地方開始各畫各的。

### 二、檢查的形式：不是比兩張圖，是問「option 有沒有忠實編碼 spec」

**實際發生過的漂移，錯的都在 option 那一側** —— 因為 PNG 每天有人看、網頁沒有。
所以靜態軌被當成參考實作，四條斷言全部從真實事故反推：

| 斷言 | 它當初藏住的方式 |
|---|---|
| 類別軸 `xAxis.data` 與序列長度對得上 | ECharts 按位置貼資料，錯位不報錯、整條位移 |
| waterfall 帶 `stackStrategy: "all"` | **漏掉時資料完全不變**，只有渲染行為變，每根從 0 往上長 |
| grouped／stacked 用 `barCategoryGap` 不用逐序列 `barWidth` | `barWidth` 是每一條不是一整組，兩條各 62% → 一組實佔 143% |
| `zero_line` 為真時 option 有 `markLine {yAxis: 0}` | 只有 PNG 有 |

第二條特別值得留意：**光比資料抓不到它**，必須直接斷言那個鍵。
因為 option 是存在日檔裡的，整組比對是純資料、不需要渲染，也因此能拿封存回測。

### 三、這條檢查一寫出來就抓到還活著的 bug

站上 **7 張標了 `zero_line` 的圖，只有 1 張的互動軌真的有零線** ——
而那 1 張是唯一的 timeseries。grouped_bar 4 張、scatter 1 張、waterfall 1 張全部沒有。

原因是 `_apply_zero_line` 那段程式**只寫在 timeseries 那條出口**，
而 `_echarts_new_kind` 與 scatter 早在前面就 `return` 了。
當初的測試案例剛好是 timeseries，所以**看起來修好了**——
舊規格自己記著的那句「**改一半比沒改更難發現**」就是這個。

在宣稱它是漂移之前先查過：那幾張的 option 裡沒有 markLine、沒有 markArea、
沒有 graphic、`yAxis` 也沒有任何零線設定 —— **沒有替代編碼**，零線只存在於 PNG。

修法是抽成共用函式讓三條出口都經過，讓「哪一種圖型」不再是變因。
`gauge` 與 `heatmap` 排除，條件與 `render_static()` 第 408 行逐字相同。

**驗收有三層**：

| 問題 | 答案 |
|---|---|
| 四種圖型都補上了嗎 | 1/7 → **7/7** |
| 原本對的那張有沒有被弄壞 | 沒有 |
| **有沒有順手改到別的東西** | 65 張圖重建 option，把零線 markLine 拿掉後**全部與原檔逐字相同** |

第三列才是「我只改了我以為我改的東西」的證據。歷史封存不回頭改寫，
所以站上那 6 張的互動軌維持原樣，而檢查在生產時只跑當日。

### 四、我替自己造了一個死連結

`SKILL.md` 裡寫著「取數眉角在 `scripts/chart/preamble.md`」，而那個檔案不存在。
更根本的是**那個形狀是錯的**：preamble 存在的理由是「採集 subagent 讀不到 brief」，
而 chart 是單一代理跑完五張圖 —— `subagent`／`子代理`／`派工` 在舊 brief 與
MAINTENANCE 裡**零命中**。我照抄 advisory 的骨架時沒問它適不適用。

改成 `chart/SOURCES.md`：一份**第 3 步才需要、靠指標到達**的參考檔，
不隨每次執行載入 —— 這樣 `BRIEF.md` 也留得住預算（實測 ~2,354 token，預算 4,000）。

順手寫了一段掃描，把 chart 這一套所有文件裡的相對路徑指標抓出來對存在性。
**它立刻抓到 `BRIEF.md` 裡還有第二處沒改** —— 我只修了 SKILL。
> **一個指標指向不存在的檔案，比沒有指標更糟**：它讓讀的人以為那份東西存在，
> 然後去別的地方找一個不存在的答案。

### 五、還沒做

1. **`tools/` 的去留** —— 架構定案是「兩軌都留」，所以 `chartkit.py` 不必重寫，
   問題只剩「它該住在資料 repo 還是 kb-core」。
   **這會動到每天 11:00 的關鍵路徑，建議明天那兩輪跑完再動。**
2. **`fetch.py`／`prefetch.py`** 同上。
3. 排程 plist 尚未安裝（`com.kenny.kbpublish.chart`），所以 chart 目前不會自動跑。

## 2026-08-20 收尾｜搬家的最後一哩、以及退休一個檢查腳本時差點掉的六條

### 一、`tools/` 清空了，殘骸留在 `_to_delete/`

`chart-of-the-day/tools/` 底下 16 個檔案全部移進 `tools/_to_delete/`（工具刪不了檔，
只能搬）。11 支 `.py` 逐檔比對過與 `kb-core/scripts/chart/` 的差異 ——
**全部只差在 repo 解析那一段**（舊制 `os.path.dirname(...)` 猜自己在資料 repo 底下，
新制走 `_repo.py` 明確傳入），沒有任何一支帶著沒搬過去的修正。

`dashpush-auto-push.sh`／`dashpush-repos.txt` 沒有新家 —— 推送改走
`publish.py` 的 outbox 草稿與回執，那條路會驗檢查、會留退出碼，
舊的背景推送兩者都沒有。

### 二、退休 `check_day.py` 之前，逐條比對它的每一個 `bad()`

**這一步差點被跳過。** 「它已經被 `checks/chart.py` 取代」是我自己寫在待辦清單上的
一句話，而那句話當時沒有任何證據 —— 12 條新檢查 vs 26KB 的舊腳本，
我沒有比對過就把它歸類成「superseded」。

實際比對 41 個 `bad()` 之後，**有六條在新檢查裡完全沒有對應的**：

| 補進去的檢查 | 它守的是什麼 | 沒有它會怎樣 |
|---|---|---|
| `chart.provenance` | 重製圖的 `inspired_by` 有 url、有原文日期、不在未來、七天內 | 重製的「題」變成沒有出處，而圖照樣畫得出來 |
| `chart.series_wellformed` | dates 與 values 等長、點數 ≥20、marker 只上有日期軸的圖型 | **類別軸寫了 marker 不報錯也不畫**，而 `reading` 會照著寫「已標在圖上」 |
| `chart.png_present` | 宣稱的 PNG 真的在磁碟上，且大於 20,000 位元組 | **空白圖不會拋例外** —— 檔案合法、只是上面沒有線 |
| `chart.prefetch_fresh` | 宣稱走 prefetch 時狀態檔在 30h 內，且序列不在失敗清單裡 | 用舊快取的那一輪**照樣會成功** |
| `chart.data_path_streak` | 連續走 browser 備援不超過 3 期 | 2026-08-06 起連九天「降級但成功」，沒有人把它當成故障 |
| `chart.release_day` | 發布日的當日主圖 slug 與 theme 對得上 | 這條規則一個月只觸發約三次，**漏掉不會有人發現** |

> **少掉的檢查不會報錯，只會全綠。** 一套檢查被另一套取代的時候，
> 「新的比較好」與「新的涵蓋了舊的」是兩個問題，而只有後者能讓舊的安全地死。

三條需要摸磁碟的（PNG 位元組、預抓狀態檔、近 14 期的 `data_path`）由
`systems/chart.py` 的 `build()` 取進 payload，檢查本身仍然不做 IO。
**取不到一律留 `None` 讓檢查判 SKIPPED** —— 給 0 或給空 dict 會讓
「沒量到」長得跟「量到了而且沒問題」一模一樣。

### 三、`prefetch_fresh` 的參照點：一條在回測裡永遠紅的檢查等於沒有

第一版拿 `now` 算快取年齡，於是回測 08-17 那天得到「已 59 小時未更新」——
**那是回測本身的產物，不是那天的事實**。改成用該輪的名目時刻
（日期＋`anchors.schedule.run`）當參照。

順著改出第二件事：狀態檔只有一份、會被後面的輪次覆寫，所以回測舊日期時
它常常**晚於**那一輪。那種情況答不出「當時新不新鮮」，回 SKIPPED 並說出原因 ——
判 PASS 等於拿一份根本不是那一輪用的快取替它背書。

回測驗收：08-17 全綠（17 PASS／1 SKIPPED），08-13 只剩那條已知的
`option_matches_spec`（歷史封存不回頭改寫）。檢查總數 61 → **67**，四套系統。

### 四、預抓終於有 plist 了

`kb-core/launchd/kbprefetch-chart.sh` ＋ `com.kenny.kbprefetch.chart.plist`（11:00）。
舊版住在資料 repo、假設 cwd 就是 repo；新版明寫 `CHART_REPO`，
**刻意不猜** —— 猜錯的樣子是「抓到了、寫進另一個目錄」，而那一輪看起來會是成功的。

查現況才發現這件事有多實在：`data/_prefetch_status.json` 停在
**2026-08-18T11:06，`host` 是 `MacBook-Pro.local`** —— 舊機器。
新的 Mac mini 從來沒跑過預抓，而在補上 `chart.prefetch_fresh` 之前，
**這件事不會出現在任何一條檢查裡**。

### 五、資料 repo 的四份舊文件掛了退場橫幅

`README.md`／`AGENT_BRIEF.md`／`MAINTENANCE.md` 頂上加了指向 kb-core 的對照表。
它們還沒刪，因為 `MAINTENANCE.md` 裡還有一些事故紀錄沒搬完 ——
但**照它做已經不行了**（那裡寫的 `python3 tools/check_day.py` 現在跑不動）。

### 六、還沒做

1. **chart 沒有每日執行者。** advisory 與 podcast 各有一個 Cowork 桌面排程，
   chart 還沒有 —— 也就是說 11:00 的預抓與每 60 秒的發布都就位了，
   **中間那一段沒有人跑**。
2. **chart 沒有任何看門狗。** 兩支 `kbwatch` 都不看它，發布鏈斷掉在 chart 這一套仍然是靜默的。
3. `MAINTENANCE.md` 的事故紀錄搬進 kb-core，然後那四份舊文件才能真的刪。

## 2026-08-20 深夜｜第一次真的按下預抓，它安靜了二十分鐘

裝好 `com.kenny.kbprefetch.chart` 之後手動驗證，終端機二十分鐘沒有任何輸出。
從快取目錄看得出來**一條 CSV 都沒被寫進去** —— `fetch.get()` 只在成功時寫檔，
失敗會拋例外、什麼都不留，所以「全部失敗」與「還在跑」在磁碟上長得一模一樣。

成因：**新的 Mac mini 上沒有 FRED 與 Tiingo 的金鑰。** 換機器時沒跟著走 ——
它們刻意不進版控，於是 `git clone` 拿不到、`git status` 也不會提。
沒有 key 就退到 `fredgraph.csv`，而 `SOURCES.md` 早就記著
**在這台機器上退路才是壞的那一條**（Errno 60），於是 46 條各自逾時 30 秒。

> 這是 `pmset` 那條教訓的第二個實例：**repo 裡看不到、換機器不會跟著走、
> 壞掉的樣子是「一切正常，只是沒有產出」。** 已寫進 `launchd/README.md`。

### 兩個都補進包裝腳本

**一、起飛前問金鑰。** 讀不到就 `exit 14`（ENVIRONMENT）中止。
刻意只問「讀不讀得到」而不打網路 —— key 錯的話 FRED 回 400 很快，
真正會拖死的只有「根本沒有 key」這一種。**這個問題要在兩秒內問完。**

**二、`--quiet` 改成看有沒有人在。** `[ -t 1 ]` 為真就逐條印，launchd 跑才只印摘要。

> **沉默同時符合「跑得好」與「全部失敗」。** 原本的寫法對 launchd 是對的
> （日誌不該每天多 46 行），對站在終端機前面的人卻是最壞的 ——
> 他唯一能做的判斷是「看起來像當掉了」，而那個判斷是錯的。
> 一個旗標服務誰，取決於誰在讀輸出，不是取決於誰在呼叫它。

台股那兩條（證交所、櫃買）免金鑰，所以這個病的典型樣子是
**美股與總經整片消失、台股正常** —— 記在 README 裡當辨識特徵。

### 補記：拿掉 `--quiet` 之後，它還是沉默的

金鑰補齊、預抓真的跑起來了（10 分鐘寫了 15 條快取），**而終端機依然一片空白。**

成因是同一行裡的第二個決定：輸出走 `| tee -a "$LOG"`，於是 python 的 stdout
從終端機變成管道，預設由行緩衝改成區塊緩衝，要積滿好幾 KB 才吐一次。
逐條進度確實印了，只是還在緩衝區裡。加 `PYTHONUNBUFFERED=1` 解決。

> **我加的是「讓它說話」，但同一行順手把它的嘴接到一個會囤積的管子上。**
> 修好之後的症狀與沒修一模一樣，所以第二次驗證時我差一點又去查網路。
>
> 這是本輪第三次撞到同一個形狀：**守衛／量測驗到的維度比它宣稱保護的低一層，
> 而失敗長得像正常輸出。** 前兩次是 docx 的 `written` 恆等於 `len(eps)`、
> 以及 `zero_line` 只修了 timeseries 那條出口。
> 這次的變體是：**可觀測性本身也需要被觀測。**

判斷「到底有沒有在跑」不要靠螢幕，靠磁碟：

```bash
find ~/chart-of-the-day/data/series -mmin -10 | wc -l
```

`fetch.get()` 只在成功時寫 CSV，所以這個數字同時回答了兩件事 ——
**還在跑嗎**，以及**抓到的比例對不對**。

### 補記二：我在它腳下換了地板

那一輪最後噴出 `line 54: ??launchd: command not found`，取數卻是完整的（34/46）。

成因是我自己：**在腳本正在執行的當下改了那個檔案。** bash 讀 script 是邊讀邊跑、
記著位元組位移的 —— 我在前段插了 4 行（約 200 位元組）修緩衝，
python 跑完、bash 回頭繼續讀時，舊位移已經指到別的地方，
於是它讀到某一行的中段（內容剛好含 `launchd`）並試著執行它。

> **在指令列上改一支正在跑的 shell script，等於在它腳下換地板。**
> 正確做法是改到暫存檔再 `mv` 過去 —— 原子改名讓還在跑的行程繼續用舊的 inode。
> 這跟「已發布的日檔不改寫」是同一條規則的不同面：
> **有東西正在讀它的時候，就不要原地改它。**

實質影響只有末三行沒跑到（結束時間那行日誌與退出碼）。**這次是良性的**，
但同樣的錯發生在 `publish.py` 或 `podcast_docx.py` 執行中就不是了。

### 基準對照

| | 2026-08-16（舊機） | 2026-08-20（Mac mini） |
|---|---|---|
| ok/requested | 34/46 | **34/46** |
| 失敗 | ^GSPC | ^GSPC（Yahoo 哨兵，設計如此） |
| 已知被擋、走替代品 | 11 | 11 |
| 耗時 | 8 分 53 秒 | 5 分 23 秒 |
| host | MacBook-Pro.local | Mac-mini.local |

搬機之後第一次全鏈路對上基準。**明天 11:00 的 launchd 輪次才是 `PYTHONUNBUFFERED`
與那三行末尾的真正驗收** —— 今晚這一輪跑的是修改前的版本。

## 2026-08-21｜首輪跑完，以及一支從來沒成功過的哨兵

首輪 11:30 起、13:09 交回執，`chart_verify` **18 PASS · 0 FAIL**。
`about.data_path=prefetch`，預抓 11:00:01–11:06:51、34/46，本期 14 條序列全在成功清單內。

### 一、`series_freshness` 修好之後，用真檔驗過它真的會叫

它原本讀 `data`／`points`，而產出寫的是 `dates`／`values` —— 對著 13 天封存全綠、
一個數字都沒讀到。改成先認 `dates` 之後，拿今天的真檔做三段測試：
**落後 1 天 PASS、3 天 WARN、9 天 FAIL**，門檻 `daily_warn_days=2`／`daily_fail_days=5`。

第一次測沒有分辨力（弄壞前後都 WARN），成因是**我的測試腳本錯了**：
`_freshness` 取的是日期陣列的**最大值**，我只改最後一格，最大值還是倒數第二個。
> **一個測不出差別的測試，跟一個沒有守門人的檢查，輸出長得一模一樣。**

### 二、18 條檢查全部做了突變測試

拿今天的真檔逐條把它宣稱守護的東西弄壞，**18/18 都轉紅**。
這是 selftest 抓不到的那一半：fixture 是手寫的，跟程式照同一個心智模型，
兩邊自洽也可能一起錯（`series_freshness` 正是如此）。

另做了兩種掃描：**鍵名稽核**（檢查取用的鍵 vs 真實產出的鍵）三套皆零真陽性；
**讀取追蹤**（把 `doc` 包成會記錄自己被讀了哪些鍵的 dict）抓到
`advisory.dispatch_wellformed` 一個產出欄位都沒讀 —— 那條是設定檢查，已改寫 `covers`。

### 三、哨兵：caller 漏了 `permissions`

`sentinel/heartbeat.json` 在遠端是 **404**。查 Actions API：這支從 2026-08-20 13:10
建立以來只跑過一次（今天 07:59Z），結論 `startup_failure`。
比對三份 caller 才看出來：advisory 與 podcast 都有

```yaml
    permissions:
      contents: write
      issues: write
```

**只有 chart 沒有。** 被呼叫的 workflow 在自己那份裡宣告的權限是「請求」，
實際能拿到多少由 caller 決定。已補上。

同時補了 `com.kenny.kbwatch.chart` —— 在此之前**兩支 kbwatch 一支看 advisory、
一支看 podcast，沒有人看 chart**，所以「哨兵從來沒有心跳」這件事
不會出現在任何一條檢查裡。發現它的是「為什麼這個檔不存在」。

### 四、我把哨兵當診斷工具跑，在三個 repo 裡各偽造了一次心跳

`sentinel.py` **會寫檔**（它是哨兵本體，不是驗證器）。
`chart_verify.py` 的 docstring 寫著「完全無副作用」，我把那個屬性套到了 sentinel 上。
> **在拿一支程式當診斷之前，先問它寫不寫檔** —— 而不是假設同一個目錄下的東西性質相同。

三份都已還原（`git checkout -- sentinel/`；chart 那個目錄本來就不存在，直接刪）。

### 五、記下一個檢查程式照不到的軟失敗

靜態軌的末值標籤會與右軸刻度疊印（今天圖 3 的 `415.26` vs `4.90`）。
新增 `anchors.known_limits` 收這一類：**跟 `known_exceptions` 不同**，
那個是「舊期豁免」，這個是「現在就是這樣，而且檢查程式看不到」。
**還沒修** —— 疊不疊印取決於字型與 DPI，沙箱字型跟 Mac 不同，
在沙箱裡「修好了」不構成證據。

### 六、還沒做

1. **`~/advisory-knowledge-hub` 舊 checkout 還在 Mac 上**，停在 2026-08-18。
   今天首輪的報告寫著「含一次走錯上游路徑」—— **它已經真的害人一次了。**
2. 末值標籤疊印（見第五節），要在發布機上出圖比對才能修。
3. 08-18～08-20 沒有封存檔，`index.json` 現為 14 期。不回補。
