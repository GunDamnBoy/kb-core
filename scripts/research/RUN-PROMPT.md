跑這一期的外資報告盤點。這是全新工作階段、沒有任何記憶，以下是全部的輸入。

**正本在 `kb-core/scripts/research/RUN-PROMPT.md`。** 排程裡那份是副本，
改動一律先改版控那份再整份貼過去。

## 這一期是哪一週

**週次取「昨天」所屬的 ISO 週**，不是今天的。排程在週一早上跑，
而要盤點的是**剛結束的那一週**（週一到週日）—— 取今天會開一個空的新週。

```
~/.venvs/kb/bin/python -c "import datetime as d;print('%d-W%02d'%(d.date.today()-d.timedelta(1)).isocalendar()[:2])"
```

手動觸發時如果要補的是更早的一週，直接把週次寫死在指令裡。

## 第 0 步：連資料夾

需要兩個 —— `kb-core`（規格、門檻、程式）、`broker-research`（報告與抽取結果）。

**沒有 `outbox`，這一套不發布。** 原文逐頁蓋有可追溯到個人的浮水印，
所以原文與抽取文字永不進任何 repo。要交的東西寫在 `broker-research/digest/`。

讀不到就自己連：`mcp__cowork__request_cowork_directory`，一次連一個。
**連不上就停下來具名回報是哪一個** —— 那跟「這週沒有新報告」在輸出上長得一樣。

## 第 1 步：入庫（純程式，你不要自己讀 PDF）

```
~/.venvs/kb/bin/python ~/kb-core/scripts/research/extract.py ~/broker-research/inbox
~/.venvs/kb/bin/python ~/kb-core/scripts/research/build_index.py
~/.venvs/kb/bin/python ~/kb-core/tools/research_verify.py
```

**第一支報孤兒時不要自己加 `--prune`**，先看它列出什麼、確認那些真的是舊 slug
留下的，再決定。刪除要明確。

`research_verify` 這時第 2 層那幾條會是 **SKIPPED 不是 PASS**（還沒做）。**有 FAIL 就停在這裡**
—— 抽取層的問題不會因為往下做而變好，只會被寫進盤點裡。

## 第 2 步：讀規格

`kb-core/research/BRIEF.md`（什麼算對的產出）與 `research/anchors.json`（每一個數字）。
**每一個門檻都從 anchors 讀，不要照印象填。**

## 第 3 步：一份報告派一個子代理

**這一套的成本結構就靠這一步。** 七份報告合計約 128 萬字元；
主代理若自己讀，一輪就爆掉。所以：**每份報告一個子代理，主代理不讀報告內文。**

派工時給子代理三樣東西，缺一不可：

1. `kb-core/scripts/research/preamble.md` 的**全文**（撰寫規則的正本）
2. 該份報告的 `extracted/<slug>.json` 路徑，與它的 `pages`
3. 交件路徑 `~/broker-research/digest/_parts/<slug>.json`

**派工指示不要重寫 preamble 裡已經寫過的規則。** 2026-08-21 首輪就是這樣壞的 ——
我在派工時多寫了一句「表格也算報告內容，寫明是第幾頁的表」，
跟 preamble 對 `grounding` 的要求相牴觸，那個子代理照我的寫，於是整份圖被擋下。
**兩份指示打架的時候，子代理聽的是比較近的那一份。**

交件形狀（就四個鍵）：

```
{"slug": "…", "summary": "…（Markdown）", "stances": [ … ], "charts": [ … ]}
```

篇幅由頁數決定（`anchors.summary_tiers`：≤10 頁 3,000／11–30 頁 4,000／>30 頁 5,000 字），
**但字數怎麼算不歸子代理管** —— `assemble.py` 會覆寫。派工時給目標，不要給算法。

## 第 4 步：組檔

```
~/.venvs/kb/bin/python ~/kb-core/scripts/research/assemble.py <YYYY-Www>
```

它做四件機械的事：覆寫 `summary_chars`、渲染圖表、組出 `file_url`、
產生給人讀的 `<YYYY-Www>.md`。**這四件都不由撰寫者填。**

`crosscut`、`watch`、`notes` 三欄由組檔程式從上一版沿用 —— 首次組檔時是空的，
**主代理在這一步把它們寫進 `<YYYY-Www>.json`，然後重跑一次 `assemble.py`**
（那三欄是主代理唯一該寫的內容，因為只有它同時看過七份的摘要）。

`crosscut` 的收錄標準只有一條：**兩家對同一件事給了不同答案，而且答案寫得出來。**
沒有分歧就寫「本週無」。**不要為了有東西寫而把「都看多」寫成分歧。**

## 第 5 步：閘門

```
~/.venvs/kb/bin/python ~/kb-core/tools/research_verify.py
```

**全綠才算完成。**（`summary_length` 出 WARN 不擋，但要在回報裡說是哪幾份、超出多少。）
紅的就回去改產出，不要改檢查。

## 這一輪不做的事

- **不跑任何 git 指令。**
- **不把原文或抽取文字複製到任何 repo 底下。**
- **不憑印象補原句。** 找不到原句就不要那一筆立場。
- **不做第 3 層（立場轉向）。** 詞表還沒訂，時候未到。
- 不代為登入任何服務。

## 回報

收了幾份、每份的券商與日期、**抽取器是哪一支**（兩軌對同一份檔可能給不同答案）、
剃除佔比與辨識的計次差距、有沒有孤兒、**每份的精華字數與它的目標區間**、
畫了幾張圖（以及有沒有渲染失敗）、寫了幾筆立場與幾條 `crosscut`、
`research_verify` 的完整結果，以及**你判斷不了而跳過的東西**。

最後把 `~/broker-research/digest/<YYYY-Www>.md` 的路徑交出來 —— **那是要讀的那一份。**

**回報你實際做到的，不是你打算做到的。**
