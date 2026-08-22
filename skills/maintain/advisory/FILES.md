# 檔案地圖與權威範圍

> **這是正本**，`maintain` 技能裡那份是副本。
>
> 上一版停在 2026-08-19 重寫之前，**而它列的 12 個檔案有 11 個不存在**
> （`AGENT_BRIEF.md`、`scripts/check.py`、`scripts/metrics.py`、`read_article.js`、
> `list_timestamps.js`、`subagent_preamble.md`、`prompts/`、`search.html`…）。
> 同一次重寫修好了 `MAIN.md` 與 `MODIFY.md`、**漏掉這一份**，
> 而 `MAIN.md` 第 2 步明寫「各檔的權威範圍見 FILES.md」——
> 指過去會拿到一份完全錯的地圖，且不會有任何徵兆。
> 2026-08-22 重寫。

第 1／2 步查漂移時對照用。**「唯一的家」欄位標了的意義沒有第二份副本 ——
任何看起來像副本的東西就是漂移。**

## 兩個 repo

| | 路徑 | 誰在推 |
|---|---|---|
| 程式與規格 | `/Users/macmini/kb-core` | `com.kenny.kbcorepush`（每 300 秒，帶閘門） |
| 已發布的資料 | `/Users/macmini/advisory-rewrite` | `com.kenny.kbpublish`（每 60 秒） |

## `kb-core`：規格

| 檔案 | 它是誰的唯一的家 | 誰在讀 |
|---|---|---|
| `advisory/anchors.json` | **每一個數字**：`groups` 十五組（名稱＋下限＋配額＋誰交）、`window`、`lengths`、`fixed_structure`、`paywall_verdict`、`collect_limits`、`collectors`（名冊與批次）、`base_card_groups`、`dedup_exempt`、`overview_prose`、`site_total`、`card_vocab` | `checks/advisory.py`、`SKILL.md` 的派工步驟、五圖的 `chart.theme_unique`（直接讀 `groups`） |
| `advisory/BRIEF.md` | **什麼算對的產出**（十節散文）＋日期檔的形狀 | 排程第 0 步、撰寫端 |
| `advisory/CHANGELOG.md` | **事故經過與被否決的選項**。每日排程不讀，維護時讀 | 維護者 |
| `scripts/advisory/preamble.md` | **採集眉角**：讀法、選擇器與路徑表、擋源三分、來源清單與**黑名單**、台股官方端點、保底數據、回報格式 | 採集 subagent（**只拿得到這一份**） |
| `skills/advisory/SKILL.md` | **每天怎麼跑**（九步）。排程裡那份是副本 | 排程（整份貼過去） |
| `checks/advisory.py` | **檢查邏輯**（17 條，suite=`advisory`）。**數字不寫在這裡**，一律從 anchors 讀 | `tools/advisory_verify.py`、`publish.py` |
| `systems/advisory.py` | payload 怎麼組、index entry 寫哪些欄、要推哪些路徑 | `publish.py` |
| `tools/advisory_verify.py` | 檢查的進入點（組 payload、取前一版、無副作用） | 人工、排程步驟 7 |
| `tools/fetch_advisory.py` | Actions 保底層取數（兩條 OAS、GLD／GLDM、台股端點）。路由表在 `kbcore/fetch_tw.py` 的 `ROUTES` | GitHub Actions（**不在本機跑，本機沒有 `FRED_API_KEY`**） |
| `tools/publish.py` | 發布流程。**三套系統共用，改它等於同時改三套** | `com.kenny.kbpublish` |
| `tools/sentinel.py` | 哨兵：日檔連續性與心跳 | `com.kenny.kbwatch` |
| `launchd/*.plist` | launchd 工作的正本；`~/Library/LaunchAgents/` 是副本，對帳指令在 `launchd/README.md` | launchd |
| `skills/maintain/advisory/*.md` | 維護流程（`MAIN.md` 入口／`MODIFY.md` 執行／本檔地圖） | 維護者 |

`kbcore/` 是三套系統共用的底盤（`report.py` 跑檢查與自檢、`result.py` 出口碼、
`system.py` 系統維度、`repo.py` git 操作、`fetch*.py` 取數）。
**動它等於同時動投顧、五圖、Podcast 三套。**

## `advisory-rewrite`：資料

| 路徑 | 內容 |
|---|---|
| `data/YYYY-MM-DD.json` | 每日封存 ＝ 那天的完整快照。**只讀不改**，更正發新的一天或掛 `errata` |
| `data/index.json` | **衍生狀態**，每輪由 `publish.py` 重建。每日 entry 帶 `thermo`／`threads`／`watch`／`pulse`／`snap` 五個**跨日記憶**欄位 |
| `raw/YYYY-MM-DD.json` | Actions 保底層當日取數。**要看的是 `fetched_at`，不是檔案在不在** |
| `index.html` | 前端外殼（含徽章表）。內容與外殼分離 |
| `sentinel/heartbeat.json`、`sentinel/report.md` | 哨兵心跳與報告 |
| `.github/` | Actions（保底層 `fetch-floor`、Pages 上線驗證） |
| `.kb-data-repo` | 系統 id `advisory-knowledge-hub`，`publish.py` 拿它做目的地守門 |

**`advisory-knowledge-hub` 是系統 id，不是路徑。**
同名的舊 checkout 已於 2026-08-21 搬到 `~/_to_delete/advisory-knowledge-hub-stale-20260818`。

## `~/outbox`：交接

`<日期>.draft.json` 由當日執行者寫入 → `publish.py` 每 60 秒掃 →
`<日期>.receipt.json` 帶 `exit`／`stage`／`commit`／`detail`。
**沒有回執與回執說失敗是兩件不同的事**：前者代表 publish 根本沒跑。

## subagent 的視野

| 角色 | 拿得到什麼 | **拿不到什麼** |
|---|---|---|
| 採集員（七個） | `scripts/advisory/preamble.md` ＋ 它那張任務卡 | **`anchors.json`、`BRIEF.md`、`SKILL.md` 全部讀不到** |
| 撰寫員（一區塊一個） | 它那張任務卡（含素材、長度門檻、組名） | 同上 |

**所以門檻類的數字必須由派工帶進任務卡** —— `paywall_verdict` 與 `collect_limits`
那六個數字就是這樣走的（`anchors` 的 `_injected_not_mirrored` 記著為什麼不讓 preamble 自己抄一份）。
**眉角類知識放 `preamble`，數字放 `anchors`，兩邊都不放對方的東西。**

拆多個撰寫員時，`deep_card_count` 與 `threaded_cards_per_day` 是**全站合計**，
派工要先分配（2026-08-22 漏分配 thread，三個分身各自合規、加起來 11 張超上限，退件一次）。

## 會安靜壞掉的幾條線

- **檢查程式讀的欄位名與產出的欄位名不同** —— 對著兩週封存全綠、一個數字都沒讀到，
  而 fixture 是同一套字典寫的、自檢照樣通過。查法是拿一期真資料手算一遍。
- **`about.run` 是自述，不是證據**（2026-08-06 自稱有 7 則 Reuters、實際 0 則）。
- **時區換算錯了不會報錯**：`ts_in_window` 只驗落不落在窗口裡，驗不出換算對不對。
  症狀是「那家今天沒新聞」（見 `preamble` 第六節華爾街見聞那一列）。
- **豁免網址的保底卡數字沒更新**：`dedup_exempt` 有五條，沒有任何機器在比對
  「今天的數字跟昨天一不一樣」（`anchors._dedup_exempt_cost`）。
- **本機重跑 `tools/fetch_advisory.py` 判斷保底層** —— 本機沒有金鑰、對外走被擋的代理，
  它會十個端點全滅，而那個結果跟 Actions 跑得如何完全無關。

## 姊妹庫

匯流條吃外部資料（Podcast 與五圖各看自己 `data/index.json` 的 `days[0]`）。
任一格從網頁上消失 ＝ 上游介面變了，轉去該系統的 `MAIN.md` 處理，在本 repo 補是補假的。
**改 `anchors.groups` 的組名會讓五圖的 `chart.theme_unique` 立刻變紅 —— 那是設計成這樣的。**
