跑這一期的外資報告盤點。這是全新工作階段、沒有任何記憶，以下是全部的輸入。

**正本在 `kb-core/scripts/research/RUN-PROMPT.md`。** 排程裡那份是副本，
改動一律先改版控那份再整份貼過去。

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

`research_verify` 這時應該只剩兩條 SKIPPED（第 2 層還沒做）。**有 FAIL 就停在這裡**
—— 抽取層的問題不會因為往下做而變好，只會被寫進盤點裡。

## 第 2 步：讀規格

`kb-core/research/BRIEF.md`（什麼算對的產出）與 `research/anchors.json`（每一個數字）。
**每一個門檻都從 anchors 讀，不要照印象填。**

## 第 3 步：讀第一頁，不要讀全文

每份報告的立場住在 `extracted/<slug>.json` 的 `page_one`。
七份合計 128 萬字元，而主張住在七頁裡 —— **這一套從第一天就不整份讀。**

`body` 只在你需要查證某個數字時才進去，而且是**指名去找那一段**，不是整份載入。

## 第 4 步：寫盤點

寫到 `~/broker-research/digest/<YYYY-Www>.json`（例：`2026-W34.json`）。形狀：

```
{"week": "2026-W34", "range": ["2026-08-17","2026-08-23"], "reports": 7,
 "stances": [{"slug":…, "broker":…, "theme":…, "quote":…, "quote_zh":…,
              "label": null, "page": 1}],
 "crosscut": "…", "watch": […]}
```

四條硬規則：

- **`quote` 是分析師的原句，一字不改。** 檢查會拿它回頭比對抽取文字，
  對不上就整輪擋下。**這是這一套唯一的防線** —— 原文不進版控，
  未來的人手上只有我們寫的東西，所以「這是他說的」與「這是我們歸納的」要永遠分得開。
- **`label` 一律填 `null`。** 立場受控詞表還沒訂，而現在訂就是訂錯
  （理由在 BRIEF 第五節）。先累積分析師自己的話。
- **`theme` 是投顧那十五組之一**，值域的家在 `advisory/anchors.json` 的 `groups`。
- **沒有原句的判斷歸到 `crosscut`**，那裡本來就是我們的話。

`crosscut` 的收錄標準只有一條：**兩家對同一件事給了不同答案，而且答案寫得出來。**
沒有分歧就寫「本週無」。**不要為了有東西寫而把「都看多」寫成分歧。**

## 第 5 步：閘門

```
~/.venvs/kb/bin/python ~/kb-core/tools/research_verify.py
```

**全綠才算完成**（`research.stance_grounded` 與 `research.theme_in_domain`
這時應該從 SKIPPED 變成 PASS）。紅的就回去改盤點，不要改檢查。

## 這一輪不做的事

- **不跑任何 git 指令。**
- **不把原文或抽取文字複製到任何 repo 底下。**
- **不憑印象補原句。** 找不到原句就不要那一筆立場。
- **不做第 3 層（立場轉向）。** 詞表還沒訂，時候未到。
- 不代為登入任何服務。

## 回報

收了幾份、每份的券商與日期、**抽取器是哪一支**（兩軌對同一份檔可能給不同答案）、
剃除佔比與辨識的計次差距、有沒有孤兒、寫了幾筆立場與幾條 `crosscut`、
`research_verify` 的完整結果，以及**你判斷不了而跳過的東西**。

**回報你實際做到的，不是你打算做到的。**
