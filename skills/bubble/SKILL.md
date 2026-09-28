---
name: bubble-weekly
description: AI 泡沫監控儀表板的每週質化覆核。每週一台北 09:00 由雲端排程執行（夾帶 ~/outbox，草稿經桌面橋接送進 outbox）；也可在互動對話說「跑這週的泡沫覆核」手動觸發。
---

# AI 泡沫監控｜這一週的質化覆核

**規格以 repo 內的 `AGENT_BRIEF.md` 為準**，這份文件只寫流程、不重複規格；
兩者衝突時以 `AGENT_BRIEF.md` 為準並在交付訊息中回報衝突。

排程開的是**全新對話、沒有任何記憶** —— 這份文件與 `AGENT_BRIEF.md` 就是全部的輸入。

**這份文件的正本在 `kb-core/skills/bubble/SKILL.md`。** 排程裡那一份是它的副本，
改動一律先改版控那份再整份貼過去。

- 網站 repo：https://github.com/GunDamnBoy/ai-bubble-monitor
  （網址 https://gundamnboy.github.io/ai-bubble-monitor/）
- 發布器的工作區：Mac 的 `/Users/macmini/Projects/ai-bubble-monitor`（**這一輪碰不到、也不該碰**，一律用 `/tmp` 的 clone）
- 發布器：`com.kenny.kbpublish.bubble` → `scripts/auto_publish.py`
  （**這一套是唯一不跑 kb-core `publish.py` 的**，plist 的版控正本在那個 repo 的 `launchd/`）

## 這一輪在哪裡跑（2026-09-28 查證）

| 段 | 在哪 | 有什麼 | 沒有什麼 |
|---|---|---|---|
| 自動指標 | GitHub Actions（每交易日＋每次 push） | 網路、重試、三層備援 | LLM |
| 質化覆核 | **這一輪：雲端容器**（排程「Bubble weekly 0900」，夾帶 `/Users/macmini/outbox`） | LLM、網路、`Bash`、`mcp__remote-devices__*`（只通到夾帶的 outbox） | git push 的權限與必要、Mac 上的 `~/Projects` |
| 發布 | Mac launchd（`auto_publish.py`） | `gate.py`＋`healthcheck.py` 兩道閘門、SSH 金鑰 | LLM |

**這一輪跑在雲端容器裡，交件要過橋。** 研究、改 `data.json`、跑 `healthcheck.py`
都在容器的 `Bash` 做；**只有「把草稿放進 Mac 的 outbox」與「讀回執」走橋**：
`mcp__remote-devices__device_commit_files`（寫）與 `mcp__remote-devices__device_bash`（讀，
路徑是 `$HOME/mnt/outbox/bubble/`）。這些工具可能是 deferred，先用 ToolSearch 載入。

**容器自己的 `~/outbox` 不是 Mac 的 `~/outbox`。** 寫進前者 `wc -c` 照樣通過，
但發布器永遠看不到 —— 沒有回執、網站不更新，而摘要看起來一切正常
（**2026-08-17 那次覆核沒發布出去就是這個形狀**）。

**如果這一輪找不到 `mcp__remote-devices__*`**（排程沒夾帶資料夾，或 Mac 的 Claude 桌面 app 沒開、
裝置離線），草稿就交不出去：照樣做完第 1–4 步，用 `SendUserFile` 把兩個檔送進對話當退路，
並在推播開頭標「⚠ 警示：草稿未能送進 outbox，網站未更新」。**不要寫進容器的 `~/outbox` 了事。**

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
來「讓它一致」**，註明「已更新 `params.X`，發布後觸發的自動更新會套用」即可（覆核上線約 1 分鐘後
push 觸發的 Actions 就會重評，不必等下一個交易日）。
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
加上第 4 步收尾八步會寫到的欄位（`zone`、`dims`、`composite`、`quadrant`、
`tw.subs`／`tw.heat`、`history` 附加一筆、`fresh`、`meta.built`／`meta.builtTime`）。

**這兩份以外一律沿用引擎寫入的值**：`events`、`triggers`，
以及所有自動指標的 `value`／`score`／`asof`。

**理由不是「連不到網路」。** 這一輪的雲端容器連得到外網（2026-09-28 實測），
執行環境換過兩次（三個環境）、網路能力每次都不同，而這條禁令一次都沒變過。
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
`set_fresh()`（`scripts/update_data.py` 的 `def set_fresh`，目前在第 111 行），不要手改 `data.json` 的 `fresh`、
也不要動 `asof` 去消音。這與「依 `score` 重算 `zone`」是同一件事，不是手動修補。

> **2026-08-23 之前這裡寫的是「`fresh` FAIL 可以照常交付」，那是個陷阱。**
> `auto_publish.py` 把 `healthcheck.py` 當閘門，**任何 FAIL 都會擋住發布**
> （`scripts/auto_publish.py` 的 gate／healthcheck 迴圈，目前在第 145–155 行，不過就 `return 5`、草稿改名成 `.parked`）。
> 那條例外是人工發布年代留下的 —— 當時沒有自動閘門，交付訊息照樣送到人手上，
> 所以「可以照常交付」是真的。**改成自動發布之後閘門變成真的（閘門在 Mac 上，這一輪跑在哪都一樣），例外就變成一個
> 讀起來合理、做下去必定被 park 的指令。** 2026-08-23 那輪的第一次投遞
> 就是這樣在 15:01 被 park（回執 exit 5），是那一輪自己認出來並改用 `set_fresh()` 的。

**完成條件**：`healthcheck.py` 的 FAIL 是 **0**，沒有例外。

## 5. 交出草稿

先在容器裡產出兩個檔，放到 `/mnt/user-data/outputs/`（`device_commit_files` 的 `stagedPath` 只收這個目錄）：

```
/mnt/user-data/outputs/data-<今天>.json     ← cp 自 /tmp/bubble-<今天>/data.json
/mnt/user-data/outputs/index-<今天>.html
```

`index-<今天>.html` 的做法：以 repo 最新 `index.html` 為基底，把
`<script type="application/json" id="dashboard-data">` 的內容整段替換為新 `data.json`
（注意屬性順序是 `type` 在前、`id` 在後），**並把內嵌那份的 `history` 裁到最後 60 筆**
（healthcheck 超過 60 筆會 WARN）。這是 fetch 失敗時的離線退路，版本必須與 `data.json` 一致。
換完先 `json.loads` 驗一次那段內嵌 JSON。

然後**一次** `device_commit_files` 寫進 Mac（`index` 放在 `data` 前面）：

```
/Users/macmini/outbox/bubble/index-<今天>.html   ← stagedPath /mnt/user-data/outputs/index-<今天>.html
/Users/macmini/outbox/bubble/data-<今天>.json    ← stagedPath /mnt/user-data/outputs/data-<今天>.json
```

**檔名一定要是這兩個格式** —— `auto_publish.py` 的 glob 認的就是
`data-YYYY-MM-DD.json`，並會把同日期的 `index-YYYY-MM-DD.html` 一併套用成 `index.html`。

寫完用 `device_bash` 在 `$HOME/mnt/outbox/bubble/` 跑 `wc -c` 與 `md5sum`，
**跟容器裡那兩份比對**——比的是 Mac 上那份，不是容器裡那份。

**不要自己 `git push`**（雲端本來就推不動，也不要找繞路）。發布的閘門
（`gate.py` 與 `healthcheck.py`）在 `auto_publish.py` 裡。
**你的工作是把檔案放到那個目錄，不是把它送上線。**

**完成條件**：`device_bash` 看得到 Mac 的 outbox 裡兩個檔，位元組數與 md5 跟容器那份相符。

## 6. 等回執

`auto_publish.py` 每 60 秒掃一次，回執在 Mac 的 `~/outbox/bubble/<今天>.receipt.json`，
**`exit` 0 才算上線**。用 `device_bash` 輪詢（例如每 10 秒看一次、最多約 3 分鐘，
單次呼叫上限 180 秒），讀到就 `cat` 出來，再 `tail` 一下 `publish.log`。

**沒有回執**與**回執說失敗**是兩件不同的事：前者先看 `.heartbeat`
（被覆寫成剛剛的時間＝發布器活著，只是還沒輪到；很舊＝launchd 沒在跑），
後者看 `publish.log`。**空的 log 與沒跑過長得一模一樣**，所以先看心跳再下結論。

**完成條件**：手上有一份回執，且它的 `exit` 有被讀過。

## 7. 交付訊息（精簡）

綜合溫度與上週比較、象限 `regime` 變化、觸發器點亮數變化、跨區指標、
`stage` 檢查清單變化、本週焦點 2–3 條、網站連結。

**讀數要標明是「覆核當下、自動更新前」的。** 發布器推的 commit 含 `index.html`，
會觸發 Actions 的 `push` 事件，**約 1 分鐘後**引擎就重算一輪（自動指標換新值、
觸發器重評、`meta.builtTime` 改回自動更新）。所以摘要的 `composite`／觸發器數字
幾分鐘內就可能差一兩分；寫一句「發布後的自動更新可能再動一兩分」即可。

**末行寫發布狀態**：回執 exit 0 就寫「已上線」並附 commit。

**開頭標「⚠ 警示」的條件只看資料**：溫度週變動 ≥5、任一指標轉紅、或觸發器新點亮。
流程異常要警示的還有 healthcheck FAIL 不是 0（第 4 步卡住）、沒有回執、
以及這一輪沒有 `mcp__remote-devices__*`（草稿交不出去）。

**上週基準是「日期 ≤ 今天−7 的最後一筆」`history`，不是倒數第二筆**（§8.2）——
`history` 每個交易日一筆，倒數第二筆只是前一個交易日。`composite` 讀它；
`regime` 用它的 `quad` 套 §3.3 反推；觸發器點亮數讀它的 `trig`。
**「觸發器新點亮」＝基準那一筆時未亮、現在亮**；週間亮滅閃爍（例如 `gsy150` 在 150% 門檻附近）
不算新點亮，摘要裡寫一句即可。

---

## 這一套的既有跳點與特例

台股 2026-09-24 起是 15 項、**五個子群**：籌碼（融資 20 日變動、當沖占比、券資比，三項）
與新增的**槓桿**（融資占市值、維持率、信用交易占比）分開。接入那天 `tw.heat`
分兩段跳（49.4→47.3→約 43，實際落在 42.7），**兩跳都是系統改動造成的**（MAINTENANCE §4）。

更早的：台股籌碼子群自 2026-08-17 起補上**當沖占市場比重**，
且 `margin_hist` 改為自動回補 —— **補齊當天 `tw.heat` 會不連續跳一次，
那一跳是系統改動造成的，不是市場動的**（MAINTENANCE §4 有記基準值）。
同理，2026-08-23 起 `idx_hist` 修好了（此前 `elec_rel` 一直在量「未含電子指數」
而不是電子工業類指數），`elec_rel` 第一次有值加入動能子群，
**`tw.heat` 於 2026-08-23 由 46.8 跳到 44.4，那一跳也是系統改動造成的**（§6.20）。

觸發器自 2026-08-22 起有 **8 項**（`gsy150` 近期在 150% 門檻上下閃爍，見第 7 步）（新增 `sahm05`：Sahm Rule ≥0.50pp，FRED SAHMREALTIME，
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