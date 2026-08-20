跑今天的 podcast 日報。這是全新工作階段、沒有任何記憶，以下是全部的輸入。

**這份的正本在 `kb-core/scripts/podcast/DIGEST-PROMPT.md`。** 排程裡那一份是它的副本，
改動一律先改版控那份再整份貼過去。

## 第 0 步：先把資料夾連起來

連線不保證跨工作階段留存，而**失敗的樣子跟「podfetch 沒跑」一模一樣**。
所以不要假設連得上，先確認：

需要四個 —— `podcast-transcripts`（讀逐字稿）、`kb-core`（讀規格與程式）、
`outbox`（寫草稿到 `outbox/podcast/`）、`podcast-knowledge-digest`（寫帳本）。

讀不到就自己連：`mcp__cowork__request_cowork_directory`（無人值守下不會跳核准對話框）。

**四個都連不上就停下來，在回報裡具名寫出是哪一個、你試了什麼、看到什麼錯誤。**
不要用「找不到檔案」草草結束 —— 那跟「今天沒有節目」在輸出上長得一樣，
而它們是完全不同的兩件事。

## 照這三份做（全部要讀）

1. `kb-core/podcast/BRIEF.md` —— 什麼算對的產出，第七節有五條當期失敗判準
2. `kb-core/podcast/anchors.json` —— 每一個數字（篇幅層級、每集件數、受控詞表、去重）
3. `kb-core/scripts/podcast/preamble.md` —— 撰寫 subagent 的規則，派工時整份給它

## 步驟

**1. 清點**　讀 `podcast-transcripts/<今天台北日期>/manifest.json`，然後跑一次

```
~/.venvs/kb/bin/python ~/kb-core/tools/podcast_verify.py ~/podcast-transcripts
```

**它的結果要進派工單**，不是看過就算。`podfetch.no_block_repetition` 指名的集數，
那幾段的實際內容是缺的 —— 派工時要具名告訴那一集的 subagent。

2026-08-21 這條抓到三集有整段複製（其中兩集 manifest 判 OK），**而沒有人跑它**，
所以那三集是當成完整內容寫完的。**一個沒有讀者的檢查等於不存在。**

**0 集時不要產空檔案、不要動 `index.json`、不要產 Word。** 先用高頻節目
（AppleID 在 anchors 的 `quality.external_check_apple_id`）**帶 cache-buster** 外部對照一次
—— iTunes 快取過期時，日誌與真正的 0 集日一模一樣。確認之後直接回報結束。

**2. 兩種去重**　跨日（比對 `podcast-knowledge-digest/data/index.json` 最近幾天）
與同日同源（規則在 anchors 的 `dedup`）。

**兩個欄位必須同時相同才算同源**，不要只比標題、也不要做模糊比對 ——
漏判只是重複，**誤判會弄丟內容**。`⚠︎` 開頭的佔位**不算已收錄**。

**3. 分派撰寫**　每集一個 subagent。派工單必須帶：
該集逐字稿路徑、`preamble.md` 全文、目標字數與段數（依 `length_tiers` 與該集片長）、
**核心重點與金句的條數上下界**（`per_episode.takeaways` 與 `per_episode.quotes`）、
**以及第 1 步驗出來、屬於這一集的整段複製位置**。

2026-08-20 首輪十集出現 13 處超量，成因是派工單只給了 schema 沒給數量。
**數量給了之後 08-21 零超量**，所以這條有效，別拿掉。

收斂規則寫在 `preamble.md` 第一之二節（一次收斂、靠合併不靠刪、只做一次）——
**這裡不重抄**。08-21 有一集初稿超四段、逐段修剪跑了 86 輪，
一集吃掉當天三分之一的成本，而同樣長的另一集一次寫對只跑 5 輪。

產出要含 **`quotes[].original`** —— 逐字稿裡的原句、一字不改。
發布閘門會拿它回頭比對逐字稿，對不上就整輪擋下。

**4. 組檔**　`chars` 用 python 機械覆寫。**每集要帶 `minutes`**（由 `durationMs` 換算）
—— 層級是由片長決定的，而 `published` 是給人讀的字串，沒有這個欄位篇幅那條判準就判不了。

當日集數達 `per_episode.crosscut_min_episodes` 時要寫 `crossCut`。
`postscript` 帶 2–3 條觀察點，收錄標準只有一條：**這句話三個月後有可能被證明是錯的嗎？**

日期檔的完整形狀照 `BRIEF.md` 第二節，以及 `podcast-knowledge-digest/data/` 裡任何一天的舊檔。

**5. 帳本**　當日觀察點附加到 `podcast-knowledge-digest/data/observations.json`，
`status` 填「觀察中」，**既有項目一條都不改**。

**6. 交草稿**　寫到 **`outbox/podcast/<今天>.draft.json`**（子目錄，不是 `outbox/` 本身），
用 `wc -c` 確認落地。**寫檔失敗與執行成功是兩件獨立的事。**

子目錄是刻意的：投顧的 publish 每分鐘掃 `outbox/` 且非遞迴，
放錯層會被它用**投顧那組檢查**驗過然後判失敗，回執檔名還會互撞。

**7. 等回執**　publish 由 Mac 上的 launchd 每 60 秒接手，你不要自己跑。
回執在 `outbox/podcast/<今天>.receipt.json`。

**睡一次 90 秒再看，不要每 10 秒問一次。** 輪詢期間快取會過期，
下一次發問時整包對話得重新寫進快取一次 —— 2026-08-21 那五分鐘的等待
多花了 23 萬 token，**是那一輪唯一一筆「什麼事都沒做卻要付」的支出**。
publish 每 60 秒跑一次，所以 90 秒之後回執該在了；還沒在就再睡 90 秒。
連兩次都沒有才去看 `outbox/podcast/publish.log`。

`exit` 的處置：`0` 收工／`10` 改草稿／`11` 掛 errata 不要改／
`12` 停下來回報／`14` 會自己重試／`15` 停下來回報。

**8. 收工**　`exit 0` 就結束這一輪。

**Word 報告不在這一輪做。** 它由 launchd 的 `com.kenny.kbdocx.podcast`
在 04:00 從**已發布的 JSON** 機械轉出 —— 那段全程不需要 LLM，
放在這裡只會多一個資料夾依賴（`~/Documents/podcast-reports`），
而 2026-08-21 那一輪就是因為那個掛載請求被中斷、**發布 exit 0、Word 卻沒有**。

## 這一輪不做的事

- **不跑任何 git 指令（含 `git status`）** —— 會留下 `.git/index.lock` 擋住發布。
- 不推 GitHub、不動 `index.html`、不改任何歷史檔案。
- **不憑印象編造內容或引述。** 沒有逐字稿就不寫金句。
- **看到 `Speaker N` 是誠實而非失敗** —— 判定不了就寫節目名，不要猜人名。
  錯的名字是對真實人物的不實陳述，比沒有名字糟得多。
- 不代為登入任何服務。
- **前一晚的美東晚間集數收不到是設計**，不要去追，也不必每天解釋。

## 進度落後時砍什麼

依序砍，一次一項：次要節目的章節深度 → 金句取下限 →
`crossCut` 從交叉分析降為並列摘要。

**篇幅下界與去重規則不在這張清單上。它們是這套系統的定義。**

## 回報

收了幾集、每集的篇幅與層級、退到第幾層與原因、`DEGRADED` 的集數與**真正的成因**
（跳針／整段複製／掉字／截斷 —— 語速基準只決定分母，不是候選答案）、
下界例外的具名記錄、外部對照的結果、被跳過的集數與理由。

**最後附一份用量回顧**：總有效 token、八個（或當日集數個）子代理各自的用量與來回次數、
主迴圈的輪數。那四個數字要填進 `kb-core/scripts/podcast/metrics.csv` 的
`eff_tokens_k`／`subagents`／`agent_turns`／`subagent_tokens_k`
—— **在此之前那四欄沒有生產者，所以永遠是空的。**

**回報你實際做到的，不是你打算做到的。**
