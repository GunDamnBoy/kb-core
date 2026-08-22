# 執行修改

第 3 步的細節。**拿到使用者對「要改什麼」的確認之後才讀這份。**

## 改哪裡

| 要改的東西 | 動這個檔 | 連帶 |
|---|---|---|
| 什麼算對的產出、失敗判準 | `kb-core/research/BRIEF.md` | 判準若引用門檻，門檻要在 `anchors.json` |
| 任何一個數字或門檻 | `kb-core/research/anchors.json` | 見下方「來源規則」 |
| 每週怎麼跑（流程或分支） | `kb-core/scripts/research/RUN-PROMPT.md`（**正本**） | **改完整份貼進 Cowork 排程**，見下方 |
| 撰寫 subagent 的規則 | `kb-core/scripts/research/preamble.md` | `dossier.py` 內嵌那段要跟著（見 `FILES.md`） |
| 發布前檢查 | `kb-core/checks/research.py` | 見下方「新增檢查」 |
| 週期、可否改寫 | `kb-core/systems/research.py` 的 `cadence_hours`／`republish_rule` | 哨兵門檻是 `cadence_hours` 的函數，改它同時動到哨兵 |
| 抽取、剃浮水印、分欄 | `kb-core/scripts/research/extract.py` | 剃除界線的數字在 `anchors.extract` |
| 組檔、分週、選圖 | `kb-core/scripts/research/assemble.py` | 圖型對照讀 `chart/anchors.json` 的 `kinds` |
| 圖型與欄位對照 | `kb-core/chart/anchors.json` 的 `kinds` | **同時動到每日五圖**，兩套都要驗 |
| 站台版面、原句牆 | `~/broker-research-digest/index.html` | 它讀 `data/index.json` 與 `data/stances.json` 的欄位名 |
| 素材路徑 | `kb-core/scripts/research/_paths.py` ＋ plist 的 `BROKER_RESEARCH_ROOT` | **只有這一個家**，不要在別處再展開一次 `~` |

## Cowork 排程那份 prompt

它對檔案工具唯讀，只能走排程工具更新，而 `prompt` 是**整份覆寫**：
先讀目前內容，以它為基礎修改後送出完整版本。拿記憶中的版本重寫＝覆寫事故。

## anchors 的來源規則

`anchors.json` 開頭的 `_source_rule` 是硬規矩，不是說明：
**每一組都帶 `source`；門檻改動要留痕（舊值、新值、以及逼出這次改動的那份報告）；
禁止在兩個實測點之間內插。** 估算值標 `~`，未量測的標 `null` 並寫明為什麼還沒量。

分層邊界（11 頁、31 頁）目前是估計值不是量測值 —— 動它們之前先補量。

## 新增檢查

每一條檢查是一個 `Check(id, covers, blind_to, run, fixture, near_miss|no_boundary, suite)`，
**`blind_to` 必填**：說清楚這條檢查看不到什麼。

自檢契約很容易寫反：**`fixture` 要能觸發這條檢查（回非 PASS），
`near_miss` 要剛好通過（回 PASS）**，兩者方向相反。寫反會讓
`push_kbcore` 印「檢查自檢有失敗的條目」並**擋住之後所有 kb-core 推送**。

新增前先問「正常情況會不會也觸發」。**一個每天都響而且每天都該被忽略的警報，
會把該響的那次一起帶走。**

也要問「它量的是不是它宣稱保護的東西」。`chart_files_present` 只看檔案在不在、
有多大 —— **那比它宣稱保護的東西低一階**，所以才另外有 `chart_spec_wellformed`
（野村的瀑布圖規格給錯欄位、渲染出一張空圖、沒有例外、所有檢查全綠）。

## 改已發布的內容

`republish_rule` 是 `append_only`：**加新的可以，改舊的不行。**
要撤稿由使用者 `git rm` 那一期重發，**那筆 revert commit 就是要有人看得見**。
不要改草稿去繞過閘門。**一個每次都要繞過的守衛，遲早會被繞過它不該被繞過的那一次。**

## 驗證

**全數通過才算完成**；任何一項失敗就回上一步。

1. `export BROKER_RESEARCH_ROOT=~/broker-research`，重跑
   `python3 ~/kb-core/tools/research_verify.py`，確認沒有新的 FAIL。
   **沒有資料 repo 可看時三條會回 SKIPPED —— 那不是 PASS。**
2. 動過撰寫規則或閘門，拿一份既有的 `part.json` 跑
   `python3 ~/kb-core/tools/check_part.py <路徑>` 對一次。
3. 動過 `chartkit.py` 或 `kinds`，**每日五圖也要驗**：`python3 ~/kb-core/tools/chart_verify.py`。
4. 這次新增的任何量測或自動化，當場驗證它回傳非空結果（空值與 0 都算失敗）。
5. 確認 kb-core 推得出去：`tail -5 ~/outbox/kbcorepush.log`。
6. 驗線上狀態時，網址帶 cache-buster 並確認站台的更新標示。
