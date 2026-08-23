跑這一期的外資報告盤點。這是全新工作階段、沒有任何記憶，以下是全部的輸入。

**正本在 `kb-core/scripts/research/RUN-PROMPT.md`。** 排程裡那份是副本，
改動一律先改版控那份再整份貼過去。

## 這一期是哪一週

**週次取「昨天」所屬的 ISO 週**，不是今天的。

排程在**週日 23:00（台北）**跑，那是 ISO 週的最後一天，所以今天與昨天同屬一週 ——
這條規則兩種情況都對。寫成「昨天」而不是「今天」，是因為**排程時間會搬**
（它從週一早上搬過來就是一例），而搬到週一之後「今天」會開一個空的新週。
**取昨天，這條規則就不隨排程時間改變。**

```
~/.venvs/kb/bin/python -c "import datetime as d;print('%d-W%02d'%(d.date.today()-d.timedelta(1)).isocalendar()[:2])"
```

手動觸發時如果要補的是更早的一週，直接把週次寫死在指令裡。

## 第 0 步：連資料夾

需要四個 —— `kb-core`（規格、門檻、程式）、`broker-research`（報告與抽取結果）、
`outbox`（發布草稿）、`broker-research-digest`（資料 repo，圖要放進去）。

**這一套會發布，但發布的是衍生層。** 原文逐頁蓋有可追溯到個人的浮水印，
所以**原文與抽取文字永不進任何 repo** —— 那條界線是結構性的（檔案住在
所有 repo 之外），不是 `.gitignore`。上網的是精華、原句、標籤與重製圖。

讀不到就自己連：`mcp__cowork__request_cowork_directory`，一次連一個。
**連不上就停下來具名回報是哪一個** —— 那跟「這週沒有新報告」在輸出上長得一樣。

## 第 1 步：入庫（純程式，你不要自己讀 PDF）

```
~/.venvs/kb/bin/python ~/kb-core/scripts/research/extract.py ~/broker-research/inbox
~/.venvs/kb/bin/python ~/kb-core/scripts/research/build_index.py
~/.venvs/kb/bin/python ~/kb-core/tools/research_verify.py
```

**整批用同一支抽取器。** `research.one_engine` 會在混軌時出 WARN ——
兩軌對旋轉文字、欄位與空白的處理不同，混軌的一批**每一份自己都合格，
但跨份的比較不再成立**。

**既有的不要為了消掉那個 WARN 重抽。** 2026-08-22 實測：18 份全部改用
`pdftotext` 重抽，會打壞一份已經驗過的 grounding。**混軌是真的缺陷，
但為了讓燈變綠而破壞已經驗過的東西更糟。**

**第一支報孤兒時不要自己加 `--prune`**，先看它列出什麼、確認那些真的是舊 slug
留下的，再決定。刪除要明確。

**標題不是檔名。** `extract.py` 會叫 `title.py` 去 PDF 中繼資料或第一頁取真實標題，
並記下 `title_source`（`pdf_meta`／`page_one`／`filename`）。
`research.title_resolved` 看到 `filename` 就 FAIL —— 那代表**這家券商的取法還沒量過**。

遇到新券商時：先跑一次 `title.py --selftest`（對著 `~/broker-research/title_fixture.json`），
把那幾份的期望標題人工讀出來寫進 fixture，**再**去 `title.py` 加對照表。
順序不能反 —— 沒有驗證集的調參，判為成功的份數會在兩個數字之間跳，而你分不出哪次是對的。

**`product` 與 `slug` 仍然來自檔名，即使檔名是 `1317180`。** 那是身分不是顯示：
`dossier` 條目 id、圖檔名、已發布的 `data/*.json` 全部指著它。要改得另外規劃遷移。

`research_verify` 這時第 2 層那幾條會是 **SKIPPED 不是 PASS**（還沒做）。**有 FAIL 就停在這裡**
—— 抽取層的問題不會因為往下做而變好，只會被寫進盤點裡。

## 第 2 步：讀規格

`kb-core/research/BRIEF.md`（什麼算對的產出）與 `research/anchors.json`（每一個數字）。
**每一個門檻都從 anchors 讀，不要照印象填。**

## 第 3 步：一份報告派一個子代理

**這一套的成本結構就靠這一步。** 七份報告合計約 128 萬字元；
主代理若自己讀，一輪就爆掉。所以：**每份報告一個子代理，主代理不讀報告內文。**

**先替每一份組卷宗**（純程式，一份約 9 KB）：

```
for s in ~/broker-research/extracted/*.json; do
  ~/.venvs/kb/bin/python ~/kb-core/scripts/research/dossier.py "$(basename "$s" .json)"
done
```

卷宗裡有第一頁全文、內文的**頁次目錄**、以及**所有機械規則**
（字數怎麼算、原句怎麼比對、`kind` 有哪些值、`theme` 的 15 組）。
2026-08-22 量出來：不給卷宗的話，子代理平均花 18 輪盲切同一個檔、
再花 10 輪逆向工程規格 —— **每一輪約 1.5 萬到 2 萬有效 token。**

**只派沒有交件的那幾份。** `digest/_parts/<slug>.json` 已經存在的就跳過 ——
既有的精華不重寫（重寫會改到已發布的內容，`append_only` 會擋，而那是對的）。
2026-08-22 那一批 22 份裡有 18 份已經有精華，**重派等於多花十幾個子代理
去產出一模一樣的東西，然後被守衛擋下來**。

派工時給子代理三樣東西，缺一不可：

1. `kb-core/scripts/research/preamble.md` 的**全文**（怎麼寫得好）
2. 該份報告的**卷宗路徑** `~/broker-research/dossier/<slug>.md`
3. 交件路徑 `~/broker-research/digest/_parts/<slug>.json`

**不要再給 `extracted/<slug>.json` 的路徑當主要入口**，也不要重述卷宗裡的機械規則 ——
兩份說法一旦不一致，子代理聽的是比較近的那一份。

**標籤要串起來，所以派工要分批。** 每份報告 3–6 個關鍵字標籤（`tags`），
而**同義的近義詞會讓網站上同一個主題散成兩堆**（「資料中心」與「數據中心」）。
所以不要七份一次全部平行派出去：分兩到三批，
**每一批的派工指示都附上前面幾批已經用過的標籤清單**，要求先從清單裡挑。
主題重疊的兩份（例如兩份石油、兩份談聯準會）刻意排在不同批。

**派工指示不要重寫 preamble 裡已經寫過的規則。** 2026-08-21 首輪就是這樣壞的 ——
我在派工時多寫了一句「表格也算報告內容，寫明是第幾頁的表」，
跟 preamble 對 `grounding` 的要求相牴觸，那個子代理照我的寫，於是整份圖被擋下。
**兩份指示打架的時候，子代理聽的是比較近的那一份。**

交件形狀（就四個鍵）：

```
{"slug": "…", "summary": "…（Markdown）", "stances": [ … ], "charts": [ … ]}
```

篇幅由頁數決定，卷宗已經替它算好目標與區間。

**每個子代理交件前要自己跑一次 `tools/check_part.py`**（卷宗與 preamble 都寫了）——
它跑的是跟發布閘門同一套比對規則。**綠了才回報。**
上一輪十一個子代理各自寫了一次同一支比對腳本，那支現在在 `tools/` 底下。

## 第 4 步：組檔

```
~/.venvs/kb/bin/python ~/kb-core/scripts/research/assemble.py <YYYY-Www>
# 寫好 crosscut／watch／notes 之後，再跑一次：
~/.venvs/kb/bin/python ~/kb-core/scripts/research/assemble.py <YYYY-Www> --publish
```

它做六件機械的事，**沒有一件由撰寫者填**：覆寫 `summary_chars`、渲染圖表、
組出 `file_url`、產生本機的 `.md` 與 `.html`（圖已內嵌）、
組出跨期的標籤索引、寫發布草稿到 `~/outbox/research/` 並把圖複製進資料 repo。

跑完它會列出**孤兒圖檔**（不在這一期 digest 裡、卻還躺在 `charts/` 的檔）。
那些檔會跟著發布推上去，變成沒有任何頁面連到、卻公開在網路上的東西。
**這支不刪檔** —— 自己 `mv` 到 `_to_delete/`。

**這一批的報告可能橫跨好幾週。** `assemble.py` 只收該週的，其餘會列出來 ——
**那幾週要各自再跑一次**，不然它們永遠不會被收錄，而且沒有任何東西會提醒你。

`crosscut`、`watch`、`notes` 三欄由組檔程式從上一版沿用 —— 首次組檔時是空的，
**主代理在這一步把它們寫進 `<YYYY-Www>.json`，然後重跑一次 `assemble.py`**
（那三欄是主代理唯一該寫的內容，因為只有它同時看過所有報告的摘要）。

**第二次才加 `--publish`。** 不加就不會有草稿進 outbox ——
publish 每 60 秒收一次，第一次組檔就交出去的話，
**那一期會在 crosscut 還是空的時候上線**，補寫之後撞上不可改寫守衛、
然後每分鐘紅一次永遠紅下去。2026-08-22 有四期就是這樣壞的。

`crosscut` 的收錄標準只有一條：**兩家對同一件事給了不同答案，而且答案寫得出來。**
沒有分歧就寫「本週無」。**不要為了有東西寫而把「都看多」寫成分歧。**

## 第 5 步：閘門

```
~/.venvs/kb/bin/python ~/kb-core/tools/research_verify.py ~/broker-research/extracted
```

**全綠才算完成。**（`summary_length` 出 WARN 不擋，但要在回報裡說是哪幾份、超出多少。）
紅的就回去改產出，不要改檢查。

## 第 5 步之後：這一期可能已經發布過

**報告依它自己的日期分期**（使用者定的，因為他會把幾個月前的報告丟進來），
而報告不會在週末停止到達 —— 一份 8/19 完成的報告可能 9 月才進 inbox，
那時 W34 早就發布了。

這是允許的：`broker-research-digest` 的 `republish_rule` 是 **`append_only`**
（只准長大）。**加新的報告會直接寫進已發布的那一期**，回執照樣 exit 0，
log 會印一行「改寫 …，系統的 republish_rule 判定這是允許的變更」。

**被擋下來的只有一種情況**：已發布的某一份，內容被改了或不見了。
回執會指名是哪幾份（exit 11）。那時**不要自己改草稿去繞過它** ——
那條守衛擋的正是「已經給人看過的東西被悄悄換掉」。回報給使用者，
由他決定要不要 `git rm` 那一期重發（那會留下一筆 revert commit，
**那筆紀錄就是要有人看得見**）。

> 已知的一次：2026-08-22 整批換抽取器，花旗油品月報有一條 grounding
> 在新的抽取結果裡對不上，改成了另一個逐字存在的片段。
> **W34 下一次組檔會因此被 `append_only` 擋一次**，那是預期中的，
> 需要一次 `git rm data/2026-08-23.json` 重發。

## 第 6 步：發布

帶 `--publish` 重跑之後，`assemble.py` 會把草稿寫到
`~/outbox/research/<週日>.draft.json`、把圖複製到
`~/broker-research-digest/charts/<週次>/`。**你不用推任何東西** ——
`com.kenny.kbpublish.research` 每分鐘會來收，走的是跟另外三套一模一樣的發布路徑
（閘門 → 不可改寫守衛 → 原子寫入 → add → 對帳 → rebase → push）。

**發布用的草稿跟本機那份不是同一個東西**：`file` 與 `file_url`
（`file:///Users/…`）被拿掉了，因為它們對讀者沒有用，而且會把使用者的帳號名
與目錄結構寫在公開頁面上。

跑完幾分鐘後看一眼 `~/outbox/research/<週日>.receipt.json`：
**exit 0 才算上線；沒有回執代表 publish 根本沒跑**，那跟「回執說失敗」是兩件事。

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

最後交出兩樣：`~/broker-research/digest/<YYYY-Www>.html`（本機、圖已內嵌）
與**發布回執的 exit code**。

## 用量：量它，不要估它

**回報之前跑這一支。用 `Bash`（雲端容器），不是 `device_bash`** ——
逐字稿只存在於雲端那一側，在 Mac 上跑一定失敗：

```bash
cd /tmp && rm -rf kbc && git clone -q --depth 1 https://github.com/GunDamnBoy/kb-core kbc
python3 kbc/tools/usage_report.py broker-research
```

它印出主線與各子代理的有效 token、以及**一行 CSV**。
把那一行原封不動 append 到 `~/kb-core/metrics/usage.csv`（device bash）。

**不要自己估、也不要抄你以為的數字。** 代理看不到自己的 usage 欄位 ——
`podcast/metrics-columns.md` 原本那四欄寫的就是「人工，抄自當輪用量回顧」，
而**自述與量測在 CSV 裡長得一模一樣，只有一個能拿來做決定**。

它會把挑到的逐字稿檔名與時間範圍印出來。**對一眼**：
挑錯逐字稿與挑對的，算出來的數字都很合理。

**回報你實際做到的，不是你打算做到的。**
