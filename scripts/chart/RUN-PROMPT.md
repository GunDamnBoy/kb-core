跑今天的每日五圖。這是全新工作階段、沒有任何記憶，以下是全部的輸入。

## 第 0 步：先把資料夾連起來

連線不保證跨工作階段留存，而**失敗的樣子跟「預抓沒跑」一模一樣**。
所以不要假設連得上，先確認：

需要三個 —— `kb-core`（讀規格、門檻與程式）、`chart-of-the-day`（讀快取與封存）、
`outbox`（寫草稿到 `outbox/chart/`）。

讀不到就自己連：`mcp__cowork__request_cowork_directory`（無人值守下不會跳核准對話框）。

**連不上就停下來，在回報裡具名寫出是哪一個、你試了什麼、看到什麼錯誤。**
不要用「找不到檔案」草草結束 —— 那跟「今天沒有題材」在輸出上長得一樣，
而它們是完全不同的兩件事。

## 照 SKILL 做

`kb-core/skills/chart/SKILL.md` 是這一輪的完整流程，整份讀完再開始。
它會把你指到 `chart/BRIEF.md`（什麼算對的產出）、`chart/anchors.json`（每一個數字）、
`chart/SOURCES.md`（取數眉角，第 3 步才需要）。

**每一個門檻都從 `anchors.json` 讀，不要照自己的印象填。**

## 交草稿與等回執

寫到 **`~/outbox/chart/<今天>.draft.json`**（子目錄，不是 `outbox/` 本身），
用 `wc -c` 確認落地。**寫檔失敗與執行成功是兩件獨立的事。**

子目錄是刻意的：三套系統的 publish 都掃自己那一層且非遞迴，
放錯層會被別套的檢查驗過然後判失敗，回執檔名還會互撞。

publish 由 Mac 上的 launchd 每 60 秒接手，**你不要自己跑，也不要跑任何 git 指令**。
回執在 `~/outbox/chart/<今天>.receipt.json`。

`exit` 的處置：`0` 收工／`10` 改草稿／`11` 掛 errata 不要改／
`12` 停下來回報／`14` 會自己重試／`15` 停下來回報。

## 這一輪不做的事

- **不跑任何 git 指令（含 `git status`）** —— 會留下 `.git/index.lock` 擋住發布。
- **不改寫任何已發布的 `data/YYYY-MM-DD.json`。** 發布過就是封存，錯了掛 errata。
- **不憑印象編造數字。** 沒有序列就不畫那張圖，改用預抓涵蓋內的序列。
- 不代為登入任何服務。

## 進度落後時砍什麼

依序砍，一次一項：slot 4（主題深掘）改用已在預抓涵蓋內的序列 →
`reading` 取下限 → 重製圖改為並列摘要。

**五張圖的張數、slot 順序、theme 不重複與篇幅下界不在這張清單上。它們是這套系統的定義。**

## 回報

五張圖各自的 slot／theme／kind／序列來源、`about.data_path` 走的是哪一條與為什麼、
預抓涵蓋率與沒涵蓋到的序列、`chart_verify` 的完整結果（PASS／WARN／FAIL／SKIPPED 各幾條、
FAIL 與 SKIPPED 逐條列出）、回執的 exit code。

## 用量：量它，不要估它

**回報之前跑這一支**（在雲端容器跑，逐字稿在那裡；不是 device bash）：

```bash
cd /tmp && rm -rf kbc && git clone -q --depth 1 https://github.com/GunDamnBoy/kb-core kbc
python3 kbc/tools/usage_report.py chart
```

它印出主線與各子代理的有效 token、以及**一行 CSV**。
把那一行原封不動 append 到 `~/kb-core/metrics/usage.csv`（device bash）。

**不要自己估、也不要抄你以為的數字。** 代理看不到自己的 usage 欄位 ——
`podcast/metrics-columns.md` 原本那四欄寫的就是「人工，抄自當輪用量回顧」，
而**自述與量測在 CSV 裡長得一模一樣，只有一個能拿來做決定**。

它會把挑到的逐字稿檔名與時間範圍印出來。**對一眼**：
挑錯逐字稿與挑對的，算出來的數字都很合理。

**回報你實際做到的，不是你打算做到的。**
