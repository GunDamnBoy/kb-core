---
name: bubble-weekly
description: AI 泡沫監控儀表板的每週質化覆核。每週一台北 09:03 在 Mac mini 上執行；也可在互動對話說「跑這週的泡沫覆核」手動觸發。
---

# AI 泡沫監控｜這一週的質化覆核

**規格以 repo 內的 `AGENT_BRIEF.md` 為準**，這份文件只寫流程、不重複規格；
兩者衝突時以 `AGENT_BRIEF.md` 為準並在交付訊息中回報衝突。

排程開的是**全新對話、沒有任何記憶** —— 這份文件與 `AGENT_BRIEF.md` 就是全部的輸入。

**這份文件的正本在 `kb-core/skills/bubble/SKILL.md`。** 排程裡那一份是它的副本，
改動一律先改版控那份再整份貼過去。

- 網站 repo：https://github.com/GunDamnBoy/ai-bubble-monitor
  （網址 https://gundamnboy.github.io/ai-bubble-monitor/）
- 本機 repo：`/Users/macmini/Projects/ai-bubble-monitor`
- 發布器：`com.kenny.kbpublish.bubble` → `scripts/auto_publish.py`
  （**這一套是唯一不跑 kb-core `publish.py` 的**，plist 的版控正本在那個 repo 的 `launchd/`）

## 這一輪在哪裡跑（2026-08-23 改）

| 段 | 在哪 | 有什麼 | 沒有什麼 |
|---|---|---|---|
| 自動指標 | GitHub Actions（每交易日） | 網路、重試、三層備援 | LLM |
| 質化覆核 | **這一輪（Mac 桌面版）** | LLM、檔案系統、完整網路 | git push 的權限與必要 |
| 發布 | Mac launchd（`auto_publish.py`） | `gate.py`＋`healthcheck.py` 兩道閘門、SSH 金鑰 | LLM |

**這一輪跑在 Mac 上，不是雲端。** 建立排程時要**夾帶資料夾**，
否則它會被當成雲端任務丟到容器裡跑 —— 而**雲端排程 session 拿不到本機檔案**：
`mcp__remote-devices__*` 整個命名空間不存在（2026-08-23 三次獨立測量）。
**2026-08-17 那次覆核沒發布出去就是這個形狀**：沒有草稿、沒有回執、網站不更新，
而摘要看起來一切正常。

**不要用 `SendUserFile`、不要找 `mcp__remote-devices__` 工具、
不要嘗試更新 Cowork artifact** —— 本機執行沒有這些工具，也不需要。

---

## 1. 載入現況

```bash
rm -rf /tmp/bubble-$(date +%F)
git clone --depth 1 https://github.com/GunDamnBoy/ai-bubble-monitor.git /tmp/bubble-$(date +%F)
python3 /tmp/bubble-$(date +%F)/healthcheck.py
```

**在 `/tmp` 的複本上做，不要用 `~/Projects/ai-bubble-monitor`。**
那個工作區歸 `com.kenny.kbpublish.bubble` 所有，它每 60 秒在裡面做 git 操作。
在別人的工作區裡改東西，症狀會出現在**發布**那一邊，不是這一邊。
**目錄名帶日期、而且先 `rm -rf`** —— `/tmp` 的檔案會跨輪次殘留，
而「寫檔失敗」與「執行成功」是兩件獨立的事（2026-08-12 五圖那次事故的形狀）。

**動手前先完整讀 `AGENT_BRIEF.md`**，特別是 §4.5（質化評分 rubric 與 note 規則）、
§4.6（台灣供應鏈錨點）、§8（人機分工、§8.3 的白名單、收尾重算順序、交付流程）。
**規格已於 2026-08-22 拆成兩檔**：抓取實作、`data.json` schema、變更紀錄搬到
`INTERNALS.md`（章節編號不變，仍是 §5／§6／§10），覆核用不到，不必讀。

記下 `composite`、`quadrant`、觸發器點亮數當作事後對照的基準。

**完成條件**：`healthcheck.py` 跑過，現有的 FAIL 清單被記下來當基準。

## 2. 每週研究（近 7–14 天，每項都要附日期與來源）

找不到新資料就沿用舊值並**保留原本的 `asof`**（`asof` 一律是資料本身的日期；
healthcheck 因此出現過期 WARN 時，在交付訊息註明「本週已查核、無新資料」即可，
不要把 `asof` 改成今天消音）。**絕不編造數字。**

質化六項（`circular`／`weakcredit`／`vc`／`narrative`／`tokens`，
加上只在財報季動的 `cloudrev`）的計分級距與對應分數見 **`AGENT_BRIEF` §4.5**，
不要憑印象給分。

- **(a) 循環融資**（大廠對客戶／供應鏈投資、供應商融資、SPV 表外融資）→ `circular`
- **(b) 弱資質信用**（CoreWeave／Oracle CDS 或債券、AI 私募信貸壓力、再融資事件）→ `weakcredit`
- **(c) VC 與 IPO 管道**（大型輪、Crunchbase 數據、OpenAI／Anthropic IPO 進度）→ `vc`。
  **IPO 進度落在兩個地方**：`stage.checklist` 第 4 項（人讀的證據），
  以及 `megaipo` 觸發器 —— 它的 `state` 由人工旗標 `params.megaipo_done` 直接決定
  （`update_data.py` 的 `set_trig("megaipo", bool(params["megaipo_done"]), …)`），
  **所以那個旗標是這一輪要維護的**。口徑見 `AGENT_BRIEF` §3.5；
  注意 **SpaceX 2026-06-12 的掛牌不計入** —— 它不是 AI 標的。
- **(d)「AI bubble」敘事** 1–5 級（映射 10/30/50/70/90）→ `narrative`
- **(e) Token 經濟**（OpenRouter 用量、中國模型市占、token 價格戰）→ `tokens`
- **(f) 財報季**：三大雲（**1／4／7／10 月底**）營收年增 → `cloudrev`；
  NVIDIA 新 TTM EPS → `params.nvda_eps`（**NVDA 財年止於 1 月底，財報在 2／5／8／11 月下旬**，
  與三大雲錯開一個月，遇到新 EPS 就更新）。
  **沒有 `params.tsmc_eps` 這個東西** —— 台積電本益比走 TWSE 官方 BWIBBU 端點直接拿 PE。
- **(g) 月初**：讀 https://www.taifex.com.tw/cht/9/futuresQADetail 的台積電最新權重%
  → `tw.items` 中 `id=tsmc_weight` 的 `value`／`disp`／`score`／`asof`
  （**錨點見 `AGENT_BRIEF` §4.6 的台灣錨點表**，分段線性內插）。
  該站擋機器人，只能由你更新。**該頁通常只在月底更新**，抓到的值與現有 `value`
  相同就不要動，並在交付訊息註明「本次未變」。
- **(h) 每年一次**（或 FOMC 大幅調整名目 GDP 展望時）核對 `params.ngdp_nominal`
  （用於 `policy_gap` 觸發器）。官方來源是 Fed 的 SEP：名目 ≈ 實質 GDP 成長中位數
  ＋ PCE 通膨中位數。沒有新的 SEP 就原封不動，並註明「本次未動」。

**改 `params` 不會立刻反映在頁面上**（§8.2）：`nvda_eps` 要等下一次引擎跑 `nvdape`、
`ngdp_nominal` 要等下一次引擎重評 `triggers` —— **不要自己去改 `triggers` 的 `state`
來「讓它一致」**，註明「已更新 `params.X`，將於下一個交易日生效」即可。
**`megaipo_done` 是這條的例外**：它不經引擎重算，改了下一次 `set_trig` 就生效。
`params` 目前三個鍵：`nvda_eps`、`ngdp_nominal`、`megaipo_done`。

**(i) `stage` 整塊**：`checklist` 六項的 `state`／`evi`、`stage.note`，
以及 `stage.current`（1–4 的小數）、`stage.label`、`stages[]` 的 `active`／`done`。
**勾選數變了而 `current` 沒動，是最常見的漏更新。**

**`stage` 算改完的條件有三項**（§8.2）：
① 六項的 `state` 與 `evi` 都重新看過一次（沒有新證據就明講維持原判，`evi` 不必重寫）；
② `stage.note` 裡**必須有**「點亮 X／6」這一句且等於六項 `state` 的實算和
——**半格算 0.5**，句子不見或數字不符都會被 healthcheck 判 FAIL；
③ `current`、`label`、`stages[]` 的 `active`／`done` 三者互相對得上，也對得上點亮數。
**沒有機器看得到的是 `evi` 的內容與 `label` 的文字**，那兩樣只能自己重讀。

**第 4 項「AI 巨頭 IPO 潮與首日暴漲」自 2026-08-23 起是巨型 IPO 事件的唯一去處**。
注意 **SpaceX 2026-06-12 的掛牌不計入本項**：它不是 AI 標的，理由見 §3.5。

## 3. 你這一輪要碰的欄位就是白名單那兩份（§8.3）

**可以動的**：§8.2 那張清單（六項質化分數、`params`、`tsmc_weight`、`stage` 整塊），
加上第 4 步收尾七步會寫到的欄位（`zone`、`dims`、`composite`、`quadrant`、
`tw.subs`／`tw.heat`、`history` 附加一筆、`meta.built`／`meta.builtTime`）。

**這兩份以外一律沿用引擎寫入的值**：`events`、`triggers`，
以及所有自動指標的 `value`／`score`／`asof`。

**理由不是「連不到網路」。** 這一輪跑在 Mac 上，FRED／Stooq／SEC／TAIFEX
你**確實連得到** —— 2026-08-23 之前這一段寫的是雲端容器的網路限制，那條理由在這裡是假的。
**真正的理由是：一次即興抓取不是引擎那條管線。** 引擎帶重試、帶三層備援、
帶 `attempt()` 降級；你手上的是一次性的 `curl` 或 `WebFetch`。
兩者拿到的東西在 JSON 裡長得一模一樣，而**硬抓的結果是空值或殘值蓋掉好的舊值**，
下一個交易日引擎跑完才會被改回來 —— 中間那段時間網站上是錯的，而沒有任何東西會叫。

**能連得到，不代表該由你去連。**

`events` 若真的漏了重大結構性事件，最多**補 1–2 條**（附 url），不要整批重寫。

注意「重抓」≠「重算」：`dims`、`composite`、`quadrant`、`tw.subs`／`tw.heat`
都是導出欄位，質化分數一改就必須跟著重算。

## 4. 收尾重算（用 Python 寫回，順序固定，細節見 §8.4）

① 被改動指標的 `zone`（<33 綠／33–67 黃／67–84 橘／≥84 紅）
→ ② `dims`（該層非 null 指標等權平均）
→ ③ `composite`（Σ 層權重×層分數 ÷ **有值那幾層的權重和**；三層都在時分母就是 1.0）
→ ④ `quadrant` 的 `heat`／`support`／`regime`（**任一層為 null 時對應的
`heat`／`support` 也是 null、`regime` 寫「待數據」**）
→ ⑤ `tw.subs`／`tw.heat`（null 子群剔除後重新歸一）
→ ⑥ `history` 附加一筆（含 `quad` 與 **`trig`＝觸發器點亮數**，上限 400）
→ ⑦ **`fresh`**（改過 `asof` 的指標才需要）
→ ⑧ **`meta.built` 改成今天、`meta.builtTime` 改成「YYYY-MM-DD（每週質化覆核）」**。

**第 ⑧ 步不能省**：healthcheck 硬性要求 `history` 最後一筆的日期等於 `meta.built`。
**但 `meta.lastAutoRun` 絕對不要動** —— 它描述的是最後一次**自動**更新的成敗。

**`history` 只附加，永遠不改寫既有的日期或數值**；同日只留一筆。
舊筆帶 v1 的 D1–D6 鍵、或缺 `quad`／`trig` 欄，都是正常的，不要回頭補寫。

**燈號界有兩組，界線不要互相換算**：綜合溫度的分區標籤走 `zones`
（0-25 冷靜期／25-45 健康擴張／45-65 過熱警戒／65-84 泡沫化進行／84-100 極端狂熱），
單一指標的燈號走 <33／33-67／67-84／≥84 那組。頁面上同一顆 chip 兩者並用是刻意的，
但不可以拿其中一組的界線去推另一組。

**分數沒動的那幾週不必重寫 `note`**（§4.5）：`vc`／`cloudrev` 整季不動時
`note` 本來就不該重寫，硬要寫只會製造永遠修不掉的 WARN。

**每個被改動的質化指標，`note` 必須帶三件事**：上週分數 → 本週分數、變動理由、
以及**依據來源的日期與出處**（例如「FT 2026-08-01」）。
healthcheck 會檢查 `note` 裡**最後一組**軌跡的終點等於現在的 `score`（不符是 FAIL），
所以整段 `note` 只放這一個「→」箭號，其他數字對比不要用箭號。
`note` 裡沒有日期是 WARN。指標跨區時在 `note` 開頭標「本週由X轉Y」。

寫回後**再跑一次 `python3 /tmp/bubble-<今天>/healthcheck.py，FAIL 必須是 0`**。
FAIL 不是 0 就不要交付，改在交付訊息說明卡在哪一項。

### `fresh` 是導出欄位，不是例外

改了任何指標的 `asof`，`fresh` 就必須跟著重算 —— 用**引擎自己的**
`set_fresh()`（`scripts/update_data.py:109`），不要手改 `data.json` 的 `fresh`、
也不要動 `asof` 去消音。這與「依 `score` 重算 `zone`」是同一件事，不是手動修補。

> **2026-08-23 之前這裡寫的是「`fresh` FAIL 可以照常交付」，那是個陷阱。**
> `auto_publish.py` 把 `healthcheck.py` 當閘門，**任何 FAIL 都會擋住發布**
> （`scripts/auto_publish.py` 第 121 行起，不過就 `return 5`、草稿改名成 `.parked`）。
> 那條例外是雲端時代留下的 —— 當時沒有閘門，交付訊息照樣送到人手上，
> 所以「可以照常交付」是真的。**搬到本機之後閘門變成真的，例外就變成一個
> 讀起來合理、做下去必定被 park 的指令。** 2026-08-23 那輪的第一次投遞
> 就是這樣在 15:01 被 park（回執 exit 5），是那一輪自己認出來並改用 `set_fresh()` 的。

**完成條件**：`healthcheck.py` 的 FAIL 是 **0**，沒有例外。

## 5. 交出草稿

產出兩個檔案，**直接寫進 outbox**（本機執行，不過橋、不 `SendUserFile`）：

```
~/outbox/bubble/data-<今天>.json      ← cp 自 /tmp/bubble-<今天>/data.json
~/outbox/bubble/index-<今天>.html
```

**檔名一定要是這兩個格式** —— `auto_publish.py` 的 glob 認的就是
`data-YYYY-MM-DD.json`，並會把同日期的 `index-YYYY-MM-DD.html` 一併套用成 `index.html`。

`index-<今天>.html` 的做法：以 repo 最新 `index.html` 為基底，把
`<script type="application/json" id="dashboard-data">` 的內容整段替換為新 `data.json`
（注意屬性順序是 `type` 在前、`id` 在後），**並把內嵌那份的 `history` 裁到最後 60 筆**
（healthcheck 超過 60 筆會 WARN）。這是 fetch 失敗時的離線退路，版本必須與 `data.json` 一致。

寫完用 `wc -c` 確認兩個檔都落地。

**不要自己 `git push`。** 在 Mac 上你**推得動** —— 但發布的閘門
（`gate.py` 與 `healthcheck.py`）在 `auto_publish.py` 裡，繞過它就是繞過閘門。
**你的工作是把檔案放到那個目錄，不是把它送上線。**

**完成條件**：兩個檔都在 `~/outbox/bubble/`，`wc -c` 的位元組數與預期相符。

## 6. 等回執

`auto_publish.py` 每 60 秒掃一次，回執在 `~/outbox/bubble/<今天>.receipt.json`，
**`exit` 0 才算上線**。

**沒有回執**與**回執說失敗**是兩件不同的事：前者代表發布器根本沒跑
—— 這時去看 `~/outbox/bubble/publish.log`，**空的 log 與沒跑過長得一模一樣**。

**完成條件**：手上有一份回執，且它的 `exit` 有被讀過。

## 7. 交付訊息（精簡）

綜合溫度與上週比較、象限 `regime` 變化、觸發器點亮數變化、跨區指標、
`stage` 檢查清單變化、本週焦點 2–3 條、網站連結。

**末行寫發布狀態**：回執 exit 0 就寫「已上線」並附 commit。

**開頭標「⚠ 警示」的條件只看資料**：溫度週變動 ≥5、任一指標轉紅、或觸發器新點亮。
流程異常要警示的還有 healthcheck FAIL 不是 0（第 4 步卡住）、以及沒有回執。

上週基準：`composite` 看 `history` 倒數第二筆；`regime` 用倒數第二筆的 `quad` 套 §3.3 反推；
觸發器點亮數在 2026-08-10 之後的 `history` 筆直接讀 `trig` 欄，更早的筆沒有
—— 跟你在第 1 步記下的基準比。

---

## 這一套的既有跳點與特例

台股籌碼子群自 2026-08-17 起有兩項（融資餘額 ＋ **當沖占市場比重**），
且 `margin_hist` 改為自動回補 —— **補齊當天 `tw.heat` 會不連續跳一次，
那一跳是系統改動造成的，不是市場動的**（MAINTENANCE §4 有記基準值）。
同理，2026-08-23 起 `idx_hist` 修好了（此前 `elec_rel` 一直在量「未含電子指數」
而不是電子工業類指數），`elec_rel` 第一次有值加入動能子群，
**`tw.heat` 於 2026-08-23 由 46.8 跳到 44.4，那一跳也是系統改動造成的**（§6.20）。

觸發器自 2026-08-22 起有 **8 項**（新增 `sahm05`：Sahm Rule ≥0.50pp，FRED SAHMREALTIME，
唯一量實體經濟的一項）。第 7 項是 `megaipo`（OpenAI／SpaceX 巨型 IPO 完成），
**八項裡唯一沒有進度條的一項**（`prog: null`）—— 它是人工旗標，沒有可連續量測的外部數列。
其餘七項都有 `prog`。

> 舊 prompt 曾寫「2026-08-23 起第 7 項換成 `conc48`（前十大市值集中度 ≥48%）、
> `megaipo_done` 退場、白名單新增 slickcharts」。**那三件事一件都沒有落地** ——
> 2026-08-23 實測 repo HEAD（`data.json`／`update_data.py`／`healthcheck.py`／
> `AGENT_BRIEF` §3.5）全部還是 `megaipo`，整個 repo 找不到 `conc48` 這個字串。
> **這一輪照現況做，不要去實作它。** 要換是 `/bubble-maintain` 的工作。

異常處理：單項研究失敗不影響其他步驟。healthcheck 若出現
「白名單來源連續成功 ≥15 次」的 WARN，那是提醒把該來源從 §9 與 healthcheck 的
`KNOWN_FAIL` 一起移除 —— **那是維護工作階段要做的事，覆核只要提一行**。
目前白名單**兩項**：AAII 與台積電權重（`healthcheck.py` 的 `KNOWN_FAIL`，2026-08-23 實測）。
AAII 持續在 Actions 端被擋、台積電權重要人工更新。**已退場的來源不在白名單裡 —— CBOE（2026-08-17 退場）
與 CNN F&G（2026-08-22 退場）若出現在 fail 就是 healthcheck FAIL、會擋住交付**，
那是刻意的，不要當成已知正常放過。

`senti` 卡片的來源時多時少是正常的（卡片 `sub` 會誠實顯示當次合成了哪幾個），
在交付訊息回報即可，**不要自行改引擎或前端**。
要改指標、權重、資料源或網站，請 Kenny 在 Cowork 用 `/bubble-maintain` 處理。

## 用量：量它，不要估它

**收尾必做。** 規則在 `metrics/MEASURE.md`，**那是正本，這裡不抄**。

這一套的系統 id 是 `bubble`。

（2026-08-23 之前這一套完全沒有這一步，`usage_report.py` 的值域也擋著它 ——
所以 `metrics/usage.csv` 上一列都沒有。**沒有量測的系統，成本永遠是猜的。**）
